"""Django signals for PlaybookGraph model."""

import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# Fields whose changes should trigger an OpenTide metadata refresh
_METADATA_FIELDS = (
    'title',
    'goal',
    'technical_context',
    'blind_spots',
    'false_positives',
    'mitre_technique_id',
    'response_playbook',
    'default_severity',
    'alert_trigger',
    'robustness_level',
    'data_source_maturity',
)


@receiver(pre_save, sender='playbooks.PlaybookGraph')
def auto_update_opentide_metadata(sender, instance, **kwargs):
    """Auto-update OpenTide metadata before save when relevant fields change.

    This handler updates ``instance.opentide_yaml`` in memory so that the
    compiled metadata is always current before a full (no ``update_fields``)
    save.  When the caller uses ``save(update_fields=[...])`` that does not
    include ``opentide_yaml``, the metadata change will not be persisted –
    use ``RefreshOpenTideMetadata`` mutation or include ``opentide_yaml`` in
    ``update_fields`` in that case.
    """
    # Only act on existing instances that already have an opentide_yaml
    if not instance.pk or not instance.opentide_yaml:
        return

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    fields_changed = any(
        getattr(old_instance, field, None) != getattr(instance, field, None)
        for field in _METADATA_FIELDS
    )

    if fields_changed:
        logger.info(
            "Metadata fields changed for playbook %s, auto-updating OpenTide YAML",
            instance.pk,
        )
        instance.auto_update_opentide_yaml()


@receiver(post_save, sender='playbooks.PlaybookGraph')
def sync_l1_portal_snapshot(sender, instance, **kwargs):
    """Keep L1 portal snapshot current whenever a DEPLOYED workbench is saved."""
    if (getattr(instance, 'status', '') or '').upper() != 'DEPLOYED':
        return

    try:
        from playbooks.l1_portal import upsert_l1_portal_snapshot
        upsert_l1_portal_snapshot(instance)
    except Exception:
        logger.exception(
            "Failed to sync L1 portal snapshot for deployed playbook %s",
            getattr(instance, 'pk', None),
        )
