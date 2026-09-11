"""Legacy CoreTide webhook endpoint."""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)



def verify_webhook_signature(request, secret: str) -> bool:
    signature_header = request.headers.get('X-CoreTide-Signature')
    if not signature_header:
        return False

    raw_sig = signature_header
    if raw_sig.lower().startswith('sha256='):
        raw_sig = raw_sig[7:]

    expected_signature = hmac.new(
        secret.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(raw_sig, expected_signature)


@csrf_exempt
@require_http_methods(["POST"])
def coretide_webhook(request):
    webhook_secret = getattr(settings, 'CORETIDE_WEBHOOK_SECRET', None)
    if webhook_secret and not verify_webhook_signature(request, webhook_secret):
        logger.warning("Invalid webhook signature from CoreTide")
        return HttpResponse('Forbidden', status=403)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in webhook payload")
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    logger.info(
        "Ignoring deprecated CoreTide webhook payload for repository=%s commit=%s",
        payload.get('repository'),
        payload.get('commit_sha'),
    )
    return JsonResponse({
        'status': 'ignored',
        'message': 'Legacy CoreTide webhook processing has been removed; use OpenTIDE HEF publish jobs instead.',
    })
