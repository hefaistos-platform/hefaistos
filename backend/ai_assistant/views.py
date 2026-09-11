import json
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .engine import run_maieutic_questioning
from .maieutic_validation import validate_maieutic_input, get_hints_for_missing, normalize_step
from .models import UserAISettings


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def maieutic_validate(request):
	payload = request.data or {}
	step = payload.get("step") or "hypothesis"
	text = payload.get("text") or ""

	valid, missing, hints = validate_maieutic_input(step, text)

	return Response(
		{
			"valid": valid,
			"missing": missing,
			"hints": hints,
			"canSubmit": valid,
		},
		status=status.HTTP_200_OK,
	)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def maieutic_hints(request):
	payload = request.data or {}
	step = payload.get("step") or "hypothesis"
	missing = payload.get("missing") or []

	if isinstance(missing, str):
		missing = [missing]

	hints = get_hints_for_missing(step, missing)

	return Response(
		{
			"hints": hints,
		},
		status=status.HTTP_200_OK,
	)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def maieutic_ai(request):
	payload = request.data or {}
	step = normalize_step(payload.get("step") or "hypothesis")
	text = payload.get("text") or ""
	context = payload.get("context") or {}
	ai_enabled = bool(context.get("aiEnabled", True))

	if not ai_enabled:
		return Response(
			{
				"message": "AI disabled.",
				"followupQuestions": [],
				"limitReached": False,
				"aiEnabled": False,
			},
			status=status.HTTP_200_OK,
		)

	try:
		settings = UserAISettings.objects.get(user=request.user)
	except UserAISettings.DoesNotExist:
		return Response(
			{
				"message": "Please configure AI Settings in your profile first.",
				"followupQuestions": [],
				"limitReached": False,
				"aiEnabled": False,
			},
			status=status.HTTP_200_OK,
		)

	response_text, provider, _field_suggestions = run_maieutic_questioning(settings, text, None, step)
	message = response_text

	try:
		response_json = json.loads(response_text)
		message = response_json.get("socratic_question") or response_json.get("error") or response_text
	except json.JSONDecodeError:
		message = response_text

	return Response(
		{
			"message": message,
			"followupQuestions": [],
			"limitReached": False,
			"providerUsed": provider,
			"aiEnabled": True,
		},
		status=status.HTTP_200_OK,
	)
