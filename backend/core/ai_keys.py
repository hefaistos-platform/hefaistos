import hashlib
from typing import Optional
from identity.models import UserAiCredential


def get_user_ai_key(user, provider: str) -> Optional[str]:
    """
    Resolve the AI API key for a specific provider from the acting user.
    Returns the raw (currently unencrypted) value. In production, decrypt here.
    """
    if not user or getattr(user, 'is_anonymous', True):
        return None
    provider_norm = (provider or '').strip().lower()
    try:
        cred = UserAiCredential.objects.get(user=user, provider=provider_norm)
        return cred.encrypted_key  # TODO: decrypt when encryption is added
    except UserAiCredential.DoesNotExist:
        return None


def fingerprint_key(api_key: str) -> str:
    return hashlib.sha256((api_key or '').encode('utf-8')).hexdigest()
