"""TLP metadata for MISP events created from AdvOps reports."""

from playbooks.utils.tlp import normalize_tlp


def misp_tlp_policy(classification):
    value = normalize_tlp(classification)
    # Use organization distribution for restricted/unclear reports. Sharing with
    # specific recipients or clients requires a separately configured MISP group.
    distribution = {'CLEAR': 3, 'GREEN': 2}.get(value, 0)
    return f'tlp:{value.lower()}', distribution
