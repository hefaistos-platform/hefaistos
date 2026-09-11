from typing import Any, Dict, List, Optional, Tuple

from playbooks.repo_clients import RepoClient, join_repo_path, parse_repo_url


def _append_object_suffix(base_name: str, suffix: str) -> str:
    """Append ``_<suffix>`` unless the stem already ends with it."""
    expected = f'_{suffix.lower()}'
    if base_name.lower().endswith(expected):
        return base_name
    return f'{base_name}{expected}'


def _resolve_workbench_title_for_paths(playbook, mdr_data: Optional[Dict[str, Any]] = None) -> str:
    """Pick the most reliable human-readable title source for repository filenames."""
    title = getattr(playbook, 'title', None)
    if isinstance(title, str) and title.strip():
        return title.strip()

    if isinstance(mdr_data, dict):
        metadata = mdr_data.get('metadata')
        if isinstance(metadata, dict):
            meta_title = metadata.get('title')
            if isinstance(meta_title, str) and meta_title.strip():
                return meta_title.strip()

        name = mdr_data.get('name')
        if isinstance(name, str) and name.strip():
            return name.strip()

    playbook_id = getattr(playbook, 'id', None)
    return str(playbook_id or 'detection_rule')


def extract_github_details(repo_url: Optional[str]) -> Optional[Tuple[str, str]]:
    parsed = parse_repo_url(repo_url or '')
    if not parsed or parsed.provider != 'GITHUB' or '/' in parsed.namespace:
        return None
    return parsed.namespace, parsed.repo


def extract_repository_details(repo_url: Optional[str]) -> Optional[Tuple[str, str, str]]:
    parsed = parse_repo_url(repo_url or '')
    if not parsed:
        return None
    return parsed.namespace, parsed.repo, parsed.provider


def compile_opentide_bundle(
    playbook,
    target_folder: Optional[str] = None,
    *,
    ai_settings=None,
    use_ai_enrichment: bool = False,
    force_bdr_generation: bool = False,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    from playbooks.git_client import sanitize_workbench_title_for_filename
    from playbooks.utils.opentide_compiler import (
        compile_bdr_yaml_with_ai,
        compile_dom_yaml,
        compile_dom_yaml_with_ai,
        compile_mdr_yaml,
        compile_mdr_yaml_with_ai,
        compile_tvm_yaml,
        dump_opentide_yaml,
        _normalize_mdr_impacted_entities,
    )
    from playbooks.utils.opentide_validator import (
        validate_bdr_structure,
        validate_dom_structure,
        validate_mdr_structure,
        validate_tvm_structure,
    )

    tvm_data = compile_tvm_yaml(playbook)
    dom_data = (
        compile_dom_yaml_with_ai(playbook, ai_settings, use_ai_enrichment)
        if use_ai_enrichment
        else compile_dom_yaml(playbook)
    )
    mdr_data = (
        compile_mdr_yaml_with_ai(playbook, ai_settings, use_ai_enrichment)
        if use_ai_enrichment
        else compile_mdr_yaml(playbook)
    )
    _normalize_mdr_impacted_entities(mdr_data)
    bdr_data = compile_bdr_yaml_with_ai(
        playbook,
        ai_settings=ai_settings,
        force_generate=force_bdr_generation,
        use_ai_enrichment=use_ai_enrichment,
    )

    validations = [
        ('TVM',) + validate_tvm_structure(tvm_data),
        ('DOM',) + validate_dom_structure(dom_data),
        ('MDR',) + validate_mdr_structure(mdr_data),
    ]
    if bdr_data:
        validations.append(('BDR',) + validate_bdr_structure(bdr_data))

    validation_errors: List[str] = []
    for label, is_valid, errors in validations:
        if not is_valid:
            validation_errors.extend([f'{label}: {error}' for error in errors])

    if validation_errors:
        return None, validation_errors

    base_folder = (target_folder or '').strip('/')
    title_seed = _resolve_workbench_title_for_paths(playbook, mdr_data)
    safe_title = sanitize_workbench_title_for_filename(title_seed)

    tvm_path = join_repo_path(
        base_folder,
        'Objects/Threat Vectors',
        f"{_append_object_suffix(safe_title, 'tvm')}.yaml",
    )
    dom_path = join_repo_path(
        base_folder,
        'Objects/Detection Objectives',
        f"{_append_object_suffix(safe_title, 'dom')}.yaml",
    )
    mdr_path = join_repo_path(
        base_folder,
        'Objects/Detection Rules',
        f"{_append_object_suffix(safe_title, 'mdr')}.yaml",
    )

    files: Dict[str, str] = {
        tvm_path: dump_opentide_yaml(tvm_data),
        dom_path: dump_opentide_yaml(dom_data),
        mdr_path: dump_opentide_yaml(mdr_data),
    }

    bdr_path = None
    if bdr_data:
        bdr_path = join_repo_path(
            base_folder,
            'Objects/Business Rules',
            f"{_append_object_suffix(safe_title, 'bdr')}.yaml",
        )
        files[bdr_path] = dump_opentide_yaml(bdr_data)

    return {
        'files': files,
        'primary_path': mdr_path,
        'tvm_path': tvm_path,
        'dom_path': dom_path,
        'mdr_path': mdr_path,
        'bdr_path': bdr_path,
        'mdr_yaml': files[mdr_path],
    }, []


def compile_platform_rule_files(
    playbook,
    target_folder: Optional[str] = None,
    *,
    mdr_data: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    from playbooks.git_client import sanitize_workbench_title_for_filename
    from playbooks.utils.opentide_compiler import compile_mdr_yaml
    from rules.utils import extract_platform_rules_from_opentide

    mdr_data = mdr_data or compile_mdr_yaml(playbook)
    mdr_title = _resolve_workbench_title_for_paths(playbook, mdr_data)
    safe_title = sanitize_workbench_title_for_filename(mdr_title)
    rule_file_stem = _append_object_suffix(safe_title, 'mdr')
    base_folder = (target_folder or '').strip('/')
    files = extract_platform_rules_from_opentide(
        mdr_data,
        base_folder=base_folder,
        sanitized_title=rule_file_stem,
    )
    if not files:
        return None, ['No platform rules found in MDR YAML']
    return {'files': files, 'primary_path': next(iter(files))}, []


def create_github_commit(
    *,
    repo_owner: str,
    repo_name: str,
    branch: str,
    github_token: str,
    files: Dict[str, str],
    commit_message: str,
    verify_ssl: bool = True,
) -> str:
    repo_url = f'https://github.com/{repo_owner}/{repo_name}'
    client = RepoClient(
        repo_url=repo_url,
        token=github_token,
        provider='GITHUB',
        verify_ssl=verify_ssl,
    )
    return client.commit_files(branch=branch, files=files, commit_message=commit_message)


def create_repository_commit(
    *,
    repo_url: str,
    token: str,
    branch: str,
    files: Dict[str, str],
    commit_message: str,
    provider: str = 'AUTO',
    api_base_url: str | None = None,
    verify_ssl: bool = True,
) -> tuple[str, RepoClient]:
    client = RepoClient(
        repo_url=repo_url,
        token=token,
        provider=provider,
        api_base_url=api_base_url,
        verify_ssl=verify_ssl,
    )
    sha = client.commit_files(branch=branch, files=files, commit_message=commit_message)
    return sha, client
