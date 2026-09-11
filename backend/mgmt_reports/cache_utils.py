from django.core.cache import cache


MGMT_CAVE_STATS_CACHE_VERSION = 'v2'


def mgmt_cave_stats_cache_key(org_id):
    return f'mgmt_cave_stats:{MGMT_CAVE_STATS_CACHE_VERSION}:{org_id}'


def mgmt_cave_stats_cache_timeout_seconds():
    # Keep stats fresh; long-lived monthly cache causes stale reporting.
    return 300


def invalidate_mgmt_cave_stats_cache(org_id):
    if org_id is None:
        return
    cache.delete(mgmt_cave_stats_cache_key(org_id))
