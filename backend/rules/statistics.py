"""Inventory summaries; recorded metadata does not establish live platform health."""
from collections import Counter, defaultdict


def summarize_readiness(rules):
    statuses = Counter()
    formats = Counter()
    deployments = defaultdict(Counter)
    playbooks = {}
    for rule in rules:
        statuses[(rule.status or '').strip().lower() or 'unknown'] += 1
        formats[rule.format] += 1
        playbook = rule.playbook
        stage = (playbook.status or '').upper() if playbook else ''
        bucket = ('deployed' if stage == 'DEPLOYED' else
                  'testing' if stage == 'TESTING' else
                  'development' if playbook else 'unlinked')
        deployments[rule.format][bucket] += 1
        if playbook:
            playbooks[playbook.pk] = playbook

    validation = Counter({'PASSED': 0, 'FAILED': 0, 'NOT_TESTED': 0, 'OUTDATED': 0})
    for playbook in playbooks.values():
        status = playbook.test_validation_status
        if status not in ('PASSED', 'FAILED'):
            status = 'NOT_TESTED'
        elif not playbook.last_tested_at or (
            playbook.updated_at and playbook.last_tested_at < playbook.updated_at
        ):
            status = 'OUTDATED'
        validation[status] += 1

    return {
        'by_status': [{'name': name, 'count': count} for name, count in sorted(statuses.items())],
        'by_format': [{'name': name, 'count': count} for name, count in sorted(formats.items())],
        'deployment_by_format': [dict(name=name, **{key: counts[key] for key in
                                 ('deployed', 'testing', 'development', 'unlinked')})
                                 for name, counts in sorted(deployments.items())],
        'validation': [{'name': name, 'count': count} for name, count in validation.items()],
        'linked_workbench_count': len(playbooks),
    }
