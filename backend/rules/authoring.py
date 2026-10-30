"""Standalone Rule Hub persistence and single-document OpenTIDE publishing."""
import copy
import difflib
import hashlib
import re

import yaml
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.db import transaction
from playbooks.repo_clients import RepoClient
from .models import DetectionRule, RuleRepository
from .opentide_schemas import OpenTideRule

PLATFORMS = {'KQL': ('kql', 'query'), 'EQL': ('elastic', 'query'),
             'SPL': ('spl', 'query'), 'WAZUH': ('wazuh', 'rule'), 'AQL': ('qradar', 'query')}


def editable_rule(user, rule_id):
    rule = DetectionRule.objects.get(pk=rule_id, organization=user.organization)
    if not (rule.author == user.username or user.role == 'ADMIN' or user.is_staff or user.is_superuser):
        raise PermissionDenied('Only the rule author or an administrator can edit or publish this rule.')
    return rule


def document_for_rule(rule):
    if rule.authoring_document is not None:
        return copy.deepcopy(rule.authoring_document)
    metadata = {'title': rule.title, 'description': rule.description or '', 'author': rule.author or '',
                'created': rule.created_at.isoformat() if rule.created_at else '',
                'modified': rule.updated_at.isoformat() if rule.updated_at else '',
                'mitre': {}, 'capability': {}, 'response': {}, 'tags': [], 'status': 'experimental'}
    doc = {'metadata': metadata, 'platforms': {}}
    if rule.format == 'OPENTIDE':
        parsed = yaml.safe_load(rule.raw_content)
        if isinstance(parsed, dict) and isinstance(parsed.get('platforms'), dict) and isinstance(parsed.get('metadata'), dict):
            doc = parsed
            original = parsed['metadata']
            doc['metadata'] = {**metadata, **original,
                               'mitre': original.get('mitre') or {'technique_id': original.get('mitre_technique')},
                               'response': original.get('response') or {'severity': original.get('severity')}}
        else:
            # Preserve legacy MDR/bundle data verbatim as custom content.
            doc['freeRule'] = {'content': rule.raw_content, 'label': 'OpenTIDE MDR', 'language': 'yaml', 'extension': 'yml'}
    elif rule.format in PLATFORMS:
        platform, key = PLATFORMS[rule.format]
        doc['platforms'][platform] = {key: rule.raw_content}
    else:
        doc['freeRule'] = {'content': rule.raw_content, 'label': rule.custom_format_label or rule.format,
                           'language': rule.editor_language, 'extension': rule.custom_file_extension}
    return doc


def validate_draft(document):
    if not isinstance(document, dict) or not isinstance(document.get('metadata'), dict) or not isinstance(document.get('platforms'), dict):
        raise ValueError('A rule must contain metadata and platforms objects.')
    if set(document) - {'metadata', 'platforms', 'freeRule'}:
        raise ValueError('Unsupported document fields; use FREE for custom content.')
    if not isinstance(document['metadata'].get('title'), str) or not document['metadata']['title'].strip():
        raise ValueError('Enter a rule title before saving.')
    if len(document['metadata']['title']) > 200:
        raise ValueError('Rule title must be at most 200 characters.')
    for key in ('description', 'author'):
        if key in document['metadata'] and not isinstance(document['metadata'][key], str):
            raise ValueError(f'Metadata {key} must be text.')
    metadata = document['metadata']
    for key in ('mitre', 'response', 'capability'):
        if key in metadata and not isinstance(metadata[key], dict):
            raise ValueError(f'Metadata {key} must be an object.')
    if 'tags' in metadata and (not isinstance(metadata['tags'], list) or not all(isinstance(tag, str) for tag in metadata['tags'])):
        raise ValueError('Tags must be a list of strings.')
    allowed = {p: key for p, key in PLATFORMS.values()}
    for platform, content in document['platforms'].items():
        if platform not in allowed or not isinstance(content, dict) or not isinstance(content.get(allowed[platform]), str):
            raise ValueError(f'Invalid platform content: {platform}')
    free = document.get('freeRule')
    if free is not None:
        if not isinstance(free, dict) or not isinstance(free.get('content'), str):
            raise ValueError('Invalid FREE content.')
        extension = free.get('extension', 'txt')
        if not isinstance(extension, str) or len(extension) > 20 or not re.fullmatch(r'[a-z0-9]+(?:[._-][a-z0-9]+)*', extension):
            raise ValueError('Enter a file extension of 1–20 characters without a path.')
        if free.get('language', 'plaintext') not in ('plaintext', 'yaml', 'xml', 'json', 'sql'):
            raise ValueError('Unsupported highlighting language.')
        if not isinstance(free.get('label', ''), str) or len(free.get('label', '')) > 80:
            raise ValueError('Custom format label must be at most 80 characters.')


@transaction.atomic
def save_draft(user, document, rule_id=None, *, ai_attributions=None):
    validate_draft(document)
    doc = copy.deepcopy(document)
    rule = editable_rule(user, rule_id) if rule_id else DetectionRule(organization=user.organization, author=user.username)
    if rule_id:
        # Serialize saves before updating the document and its per-format history.
        rule = DetectionRule.objects.select_for_update().get(pk=rule.pk)
    if rule.playbook_id:
        raise ValueError('This rule is owned by a Workbench. Use its existing editor or duplicate it for standalone editing.')
    metadata = doc['metadata']
    now = timezone.now().isoformat()
    metadata['uuid'] = str(rule.sigma_id)
    metadata['created'] = (rule.authoring_document or {}).get('metadata', {}).get('created') or metadata.get('created') or now
    metadata['modified'] = now
    if not metadata.get('response', {}).get('severity'):
        metadata['response'] = {**metadata.get('response', {}), 'severity': 'MEDIUM'}
    rule.title = metadata['title'].strip()
    rule.description = metadata.get('description', '')
    rule.status = metadata.get('status', 'experimental')
    rule.authoring_document = doc
    rule.format = 'OPENTIDE'
    rule.raw_content = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    if not rule.repository_id:
        rule.repository, _ = RuleRepository.objects.get_or_create(organization=user.organization, name='Rule Repo', defaults={'git_url': None})
    rule.save()
    from ai_assistant.rule_feedback import record_document_revisions
    record_document_revisions(user, rule, doc, ai_attributions)
    return rule


def publish_yaml(rule):
    doc = document_for_rule(rule)
    free = doc.get('freeRule')
    if free and free.get('content', '').strip():
        raise ValueError('FREE/custom content cannot be published in the supported OpenTIDE schema. Remove it or create a separate supported platform rule.')
    metadata = doc['metadata']
    payload = {'metadata': {
        'title': metadata.get('title'), 'description': metadata.get('description'), 'author': metadata.get('author'),
        'severity': metadata.get('response', {}).get('severity') or metadata.get('severity'),
        'mitre_technique': metadata.get('mitre', {}).get('technique_id') or metadata.get('mitre_technique'),
        'uuid': str(rule.sigma_id), 'status': metadata.get('status', 'experimental'),
        'tags': metadata.get('tags', []), 'created': metadata.get('created'), 'modified': metadata.get('modified'),
    }, 'platforms': {key: value for key, value in doc['platforms'].items()
                     if value.get('rule' if key == 'wazuh' else 'query', '').strip()}}
    # Validate without serializing through Pydantic: retain additional platform settings.
    OpenTideRule(**payload)
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def repository_client(user, repository_id):
    repo = RuleRepository.objects.get(pk=repository_id, organization=user.organization)
    if not repo.git_url or not repo.token:
        raise ValueError('Select a configured repository with a Git URL and access token.')
    return RepoClient(repo_url=repo.git_url, token=repo.token, provider=repo.provider,
                      api_base_url=repo.api_base_url, verify_ssl=repo.verify_ssl)


def validate_destination(branch, path):
    if not branch or branch.startswith('-') or re.search(r'[\s\x00-\x1f~^:?*\[\\]', branch) or '..' in branch or '@{' in branch:
        raise ValueError('Enter a valid existing branch name.')
    if not path or path.startswith('/') or '\\' in path or any(part in ('', '.', '..') for part in path.split('/')) or re.search(r'[\x00-\x1f?#]', path):
        raise ValueError('Enter a repository-relative file path without traversal.')
    if not path.lower().endswith(('.yaml', '.yml')):
        raise ValueError('OpenTIDE files must use .yaml or .yml.')


def digest(content):
    return hashlib.sha256(content.encode()).hexdigest()


def preview_publish(user, rule_id, repository_id, branch, path):
    rule = editable_rule(user, rule_id)
    content = publish_yaml(rule)
    validate_destination(branch, path)
    client = repository_client(user, repository_id)
    head = client.resolve_commit_sha(branch)
    previous = client.get_file_content(path, head)
    token = signing.dumps({'user': str(user.pk), 'rule': str(rule.pk), 'repo': str(repository_id),
                           'branch': branch, 'path': path, 'head': head, 'digest': digest(content)}, salt='rule-publish')
    diff = ''.join(difflib.unified_diff((previous or '').splitlines(True), content.splitlines(True),
                                      fromfile=path if previous is not None else '/dev/null', tofile=path))
    return {'content': content, 'diff': diff, 'token': token, 'unchanged': previous == content}


def publish_preview(user, token, commit_message):
    preview = signing.loads(token, salt='rule-publish', max_age=900)
    if preview['user'] != str(user.pk):
        raise PermissionDenied('This preview belongs to another user.')
    rule = editable_rule(user, preview['rule'])
    content = publish_yaml(rule)
    if digest(content) != preview['digest']:
        raise ValueError('The rule changed after preview. Preview it again before publishing.')
    client = repository_client(user, preview['repo'])
    if client.resolve_commit_sha(preview['branch']) != preview['head']:
        raise ValueError('The repository branch changed after preview. Preview it again before publishing.')
    if client.get_file_content(preview['path'], preview['head']) == content:
        raise ValueError('No changes to publish.')
    sha = client.commit_files(branch=preview['branch'], files={preview['path']: content},
                              commit_message=commit_message.strip() or f'Publish rule: {rule.title}',
                              expected_head=preview['head'])
    return sha, client.file_web_url(preview['branch'], preview['path'])
