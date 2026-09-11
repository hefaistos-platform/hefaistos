import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from organizations.billing import apply_addon_capacity
from organizations.models import OrganizationBillingProfile

try:
    import stripe
except Exception:  # pragma: no cover
    stripe = None

logger = logging.getLogger(__name__)


def _to_positive_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


@csrf_exempt
@require_http_methods(["POST"])
def stripe_billing_webhook(request):
    if not stripe or not getattr(settings, 'STRIPE_SECRET_KEY', None):
        return JsonResponse({'status': 'ignored', 'message': 'Stripe is not configured.'}, status=503)

    payload = request.body
    signature = request.headers.get('Stripe-Signature', '')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', None)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, signature, webhook_secret)
        else:
            event = json.loads(payload.decode('utf-8'))
    except Exception as exc:
        logger.warning('stripe webhook verification failed: %s', exc)
        return HttpResponse('Bad Request', status=400)

    event_type = event.get('type')
    if event_type != 'checkout.session.completed':
        return JsonResponse({'status': 'ignored', 'event': event_type})

    session = event.get('data', {}).get('object', {})
    metadata = session.get('metadata') or {}
    if metadata.get('billing_kind') != 'capacity_addon':
        return JsonResponse({'status': 'ignored', 'message': 'Not a capacity add-on session.'})

    organization_id = metadata.get('organization_id')
    session_id = session.get('id')
    stripe_customer_id = session.get('customer')

    if not organization_id or not session_id:
        return JsonResponse({'status': 'ignored', 'message': 'Missing organization/session metadata.'}, status=400)

    add_extra_users = _to_positive_int(metadata.get('add_extra_users'), 0)
    add_extra_organizations = _to_positive_int(metadata.get('add_extra_organizations'), 0)

    profile, _ = OrganizationBillingProfile.objects.get_or_create(
        organization_id=organization_id,
        defaults={
            'included_users': OrganizationBillingProfile.BASE_USERS,
            'included_organizations': OrganizationBillingProfile.BASE_ORGANIZATIONS,
        },
    )

    apply_addon_capacity(
        billing_profile=profile,
        stripe_session_id=str(session_id),
        stripe_customer_id=str(stripe_customer_id) if stripe_customer_id else None,
        add_extra_users=add_extra_users,
        add_extra_organizations=add_extra_organizations,
    )

    logger.info(
        'stripe capacity applied org=%s session=%s users=+%s orgs=+%s',
        organization_id,
        session_id,
        add_extra_users,
        add_extra_organizations,
    )
    return JsonResponse({'status': 'ok'})
