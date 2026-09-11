from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.mcs_logging import emit_security_event
from .models import PersonalAPIToken


ALLOWED_PERSONAL_API_SCOPES: set[str] = set()
# No scopes are currently issuable. `waiting_room:create` was removed when direct
# API push access to the HEFAISTOS Waiting Room was retired in favor of MISP-only
# ingestion (importWaitingCasesFromMisp pull, tag-gated on `HEFAISTOS`). The
# PersonalAPIToken infrastructure itself is left in place for future scopes.


class PersonalAPITokenSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()

    class Meta:
        model = PersonalAPIToken
        fields = (
            'id',
            'name',
            'prefix',
            'scopes',
            'status',
            'created_at',
            'last_used_at',
            'expires_at',
            'revoked_at',
        )

    def get_status(self, obj):
        if obj.revoked_at is not None:
            return 'revoked'
        if obj.is_expired():
            return 'expired'
        return 'active'


class CreatePersonalAPITokenSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    scopes = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_name(self, value):
        cleaned = (value or '').strip()
        if not cleaned:
            raise serializers.ValidationError('Token name is required.')
        return cleaned

    def validate_scopes(self, value):
        normalized = [str(scope).strip() for scope in (value or []) if str(scope).strip()]
        if not normalized:
            raise serializers.ValidationError('At least one scope is required.')
        invalid = [scope for scope in normalized if scope not in ALLOWED_PERSONAL_API_SCOPES]
        if invalid:
            raise serializers.ValidationError(f'Invalid scopes: {", ".join(invalid)}')
        return normalized

    def validate_expires_at(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError('expires_at must be in the future.')
        return value


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def profile_tokens(request):
    user = request.user

    if request.method == 'GET':
        tokens = PersonalAPIToken.objects.filter(user=user).order_by('-created_at')
        return Response(PersonalAPITokenSerializer(tokens, many=True).data, status=status.HTTP_200_OK)

    serializer = CreatePersonalAPITokenSerializer(data=request.data or {})
    serializer.is_valid(raise_exception=True)
    token_obj, raw_token = PersonalAPIToken.issue_for_user(
        user=user,
        name=serializer.validated_data['name'],
        scopes=serializer.validated_data['scopes'],
        expires_at=serializer.validated_data.get('expires_at'),
    )
    emit_security_event(
        level='informational',
        logger_name='security.mcs',
        message='Personal API token created',
        event_action='personal_api_token.create',
        event_outcome='success',
        asvs_event_code='API-TOKEN-CREATED-01',
        user_id=str(user.id),
        user_name=getattr(user, 'username', ''),
        request=request,
        extra_context={'token_id': str(token_obj.id), 'token_name': token_obj.name, 'scopes': token_obj.scopes},
    )
    return Response(
        {
            'token': raw_token,
            'token_meta': PersonalAPITokenSerializer(token_obj).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_profile_token(request, token_id):
    user = request.user
    token_obj = PersonalAPIToken.objects.filter(user=user, id=token_id).first()
    if token_obj is None:
        return Response({'detail': 'Token not found.'}, status=status.HTTP_404_NOT_FOUND)

    token_obj.revoke()
    emit_security_event(
        level='informational',
        logger_name='security.mcs',
        message='Personal API token revoked',
        event_action='personal_api_token.revoke',
        event_outcome='success',
        asvs_event_code='API-TOKEN-REVOKED-01',
        user_id=str(user.id),
        user_name=getattr(user, 'username', ''),
        request=request,
        extra_context={'token_id': str(token_obj.id), 'token_name': token_obj.name},
    )
    return Response(PersonalAPITokenSerializer(token_obj).data, status=status.HTTP_200_OK)
