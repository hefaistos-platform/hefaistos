from ai_assistant.models import UserAISettings
from ai_assistant.schema import _get_effective_ai_settings
from ai_assistant.engine import build_available
from identity.models import CustomUser

for u in CustomUser.objects.all():
    try:
        s, _ = UserAISettings.objects.get_or_create(user=u)
        eff = _get_effective_ai_settings(s)
        avail = build_available(eff)
        if avail:
            print(u.username, '->', avail)
    except Exception as e:
        pass
