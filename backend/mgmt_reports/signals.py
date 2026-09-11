"""
Signals for mgmt_reports: auto-subscribe admin/reviewer users to the monthly report mailing list.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='identity.CustomUser')
def auto_subscribe_to_mailing_list(sender, instance, created, **kwargs):
    """Auto-subscribe users with ADMIN or REVIEWER role to the mailing list."""
    from .models import ReportMailingList

    role = getattr(instance, 'role', '')
    org = getattr(instance, 'organization', None)
    if not org or role not in ('ADMIN', 'REVIEWER'):
        return

    entry, _ = ReportMailingList.objects.get_or_create(
        user=instance,
        defaults={'organization': org, 'is_subscribed': True},
    )
    # If the entry exists but was for a different org, update it and re-subscribe
    if entry.organization_id != org.pk:
        entry.organization = org
        entry.is_subscribed = True
        entry.unsubscribed_at = None
        entry.removed_by = None
        entry.save(update_fields=['organization', 'is_subscribed', 'unsubscribed_at', 'removed_by'])
    elif not entry.is_subscribed:
        # Role was elevated back to ADMIN/REVIEWER — re-subscribe automatically
        entry.is_subscribed = True
        entry.unsubscribed_at = None
        entry.removed_by = None
        entry.save(update_fields=['is_subscribed', 'unsubscribed_at', 'removed_by'])
