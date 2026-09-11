import os
import re
from collections import Counter, defaultdict

from django.core import signing
from django.http import JsonResponse

from .models import DetectionPlaybook, PlaybookGraph
from platform_data.models import MitreAttackTechnique
from rules.models import DetectionRule


TECHNIQUE_ID_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")
TECHNIQUE_ID_EXTRACT_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
GREEN = "#1a9850"
COVERAGE_TOKEN_SALT = "playbooks.coverage.layer"
COVERAGE_TOKEN_TTL_SECONDS = int(os.environ.get("COVERAGE_LAYER_TOKEN_TTL_SECONDS", "90"))


def _json_error(message, status):
	return JsonResponse({"error": message}, status=status)


def _is_valid_attack_technique_id(technique_id):
	return isinstance(technique_id, str) and bool(TECHNIQUE_ID_RE.fullmatch(technique_id.strip()))


def _extract_attack_ids_from_text(*texts):
	"""
	Extract ATT&CK technique/sub-technique IDs from arbitrary text blobs.
	Returns a set like {"T1059", "T1059.001"}.
	"""
	found = set()
	for text in texts:
		if not text:
			continue
		for match in TECHNIQUE_ID_EXTRACT_RE.findall(str(text)):
			if _is_valid_attack_technique_id(match):
				found.add(match)
	return found


def _ratio_color(ratio: float) -> str:
	ratio = max(0.0, min(1.0, float(ratio or 0.0)))
	stops = [
		(0.0, "#fff5b1"),
		(0.33, "#fee08b"),
		(0.66, "#fdae61"),
		(0.99, "#f46d43"),
		(1.0, GREEN),
	]
	if ratio >= 1.0:
		return GREEN
	for idx in range(1, len(stops)):
		left_ratio, left_color = stops[idx - 1]
		right_ratio, right_color = stops[idx]
		if ratio <= right_ratio:
			span = right_ratio - left_ratio
			pos = 0.0 if span <= 0 else (ratio - left_ratio) / span
			lr, lg, lb = int(left_color[1:3], 16), int(left_color[3:5], 16), int(left_color[5:7], 16)
			rr, rg, rb = int(right_color[1:3], 16), int(right_color[3:5], 16), int(right_color[5:7], 16)
			r = round(lr + (rr - lr) * pos)
			g = round(lg + (rg - lg) * pos)
			b = round(lb + (rb - lb) * pos)
			return f"#{r:02x}{g:02x}{b:02x}"
	return GREEN


def _extract_bearer_or_raw_token(raw_token):
	if not raw_token:
		return None
	token = str(raw_token).strip()
	if not token:
		return None
	if token.lower().startswith("bearer "):
		token = token[7:].strip()
	return token or None


def _authenticate_from_jwt(token):
	"""Authenticate user from a long-lived JWT token string."""
	token = _extract_bearer_or_raw_token(token)
	if not token:
		return None

	from django.contrib.auth import get_user_model
	User = get_user_model()

	# 1) Try django-graphql-jwt tokens (used by our login flow)
	try:
		from graphql_jwt.utils import get_payload
		payload = get_payload(token)
		# Try resolving by user_id or username depending on payload
		user_id = payload.get("user_id")
		if user_id:
			user = User.objects.filter(id=user_id).first()
			if user:
				return user
		username_key = getattr(User, 'USERNAME_FIELD', 'username') or 'username'
		username = payload.get(username_key) or payload.get('username')
		if username:
			user = User.objects.filter(**{username_key: username}).first()
			if user:
				return user
	except Exception:
		pass

	# 2) Fallback to SimpleJWT (for completeness)
	try:
		from rest_framework_simplejwt.tokens import UntypedToken
		untyped = UntypedToken(token)
		payload = getattr(untyped, "payload", None) or {}
		user_id = payload.get("user_id")
		if user_id:
			return User.objects.filter(id=user_id).first()
	except Exception:
		pass

	return None


def _authenticate_from_token(request):
	"""Authenticate user from a legacy JWT passed via `token` query param."""
	return _authenticate_from_jwt(request.GET.get("token"))


def _authenticate_from_authorization_header(request):
	"""Authenticate user from Authorization header (Bearer JWT)."""
	authorization = request.META.get("HTTP_AUTHORIZATION", "")
	return _authenticate_from_jwt(authorization)


def _generate_coverage_access_token(user):
	"""Create short-lived, coverage-scoped token for Navigator layer fetches."""
	payload = {
		"typ": "coverage_layer",
		"uid": str(user.id),
		"oid": str(user.organization_id),
	}
	return signing.dumps(payload, salt=COVERAGE_TOKEN_SALT, compress=True)


def _authenticate_from_coverage_access_token(request):
	"""Authenticate user from short-lived scoped coverage token in query param."""
	token = _extract_bearer_or_raw_token(request.GET.get("token"))
	if not token:
		return None

	try:
		payload = signing.loads(
			token,
			salt=COVERAGE_TOKEN_SALT,
			max_age=COVERAGE_TOKEN_TTL_SECONDS,
		)
	except Exception:
		return None

	if not isinstance(payload, dict) or payload.get("typ") != "coverage_layer":
		return None

	user_id = payload.get("uid")
	org_id = payload.get("oid")
	if not user_id or not org_id:
		return None

	from django.contrib.auth import get_user_model
	User = get_user_model()
	return User.objects.filter(id=user_id, organization_id=org_id).first()


def issue_coverage_access_token(request):
	"""Issue a short-lived token for ATT&CK Navigator layer URL auth."""
	if request.method != "GET":
		return _json_error("Method not allowed", status=405)

	user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
	if not user:
		user = _authenticate_from_authorization_header(request)
	if not user:
		user = _authenticate_from_token(request)
	if not user:
		return _json_error("Authentication required", status=403)

	if not getattr(user, 'organization', None):
		return _json_error("User account is not associated with an organization.", status=400)

	response = JsonResponse(
		{
			"token": _generate_coverage_access_token(user),
			"expiresIn": COVERAGE_TOKEN_TTL_SECONDS,
			"scope": "coverage:read",
		},
		json_dumps_params={"ensure_ascii": False},
	)
	response["Cache-Control"] = "no-store"
	return response


def attack_navigator_layer_json(request):
	"""
	Returns the ATT&CK Navigator layer JSON built from deployed Workbenches for the
	authenticated user's organization. This endpoint is intended to be consumed
	by the embedded Navigator via the layerURL hash parameter.

	CORS (including OPTIONS preflight and Private Network Access) is handled by
	django-cors-headers + CORSPrivateNetworkMiddleware in the middleware stack.
	"""
	# Allow session-authenticated user, short-lived coverage token, or JWT fallback.
	user = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
	if not user:
		user = _authenticate_from_coverage_access_token(request)
	if not user:
		user = _authenticate_from_token(request)
	if not user:
		user = _authenticate_from_authorization_header(request)
	if not user:
		return _json_error("Authentication required", status=403)

	if not getattr(user, 'organization', None):
		return _json_error("User account is not associated with an organization.", status=400)

	# 1) Build active enterprise ATT&CK IDs set once for filtering all sources.
	active_technique_ids = set(
		MitreAttackTechnique.objects.filter(
			domain='enterprise-attack',
			revoked=False,
			deprecated=False,
		).values_list('technique_id', flat=True)
	)

	# 2) Get deployed Workbenches in user's org.
	deployed_graphs = PlaybookGraph.objects.filter(
		organization=user.organization,
		status='DEPLOYED',
	)

	# 3) Track directly covered techniques from all supported sources.
	direct_coverage = Counter()
	source_map = {}

	def _track_coverage(tid, source_label):
		if not _is_valid_attack_technique_id(tid) or tid not in active_technique_ids:
			return
		direct_coverage[tid] += 1
		source_map.setdefault(tid, set()).add(source_label)

	# 3a) Workbench selected technique (ForeignKey mitre_technique).
	covered_by_graphs = (
		deployed_graphs.exclude(mitre_technique__isnull=True)
			.values_list('mitre_technique__technique_id', flat=True)
	)

	# 3b) Workbench node mappings.
	node_mapped_ids = (
		MitreAttackTechnique.objects
			.filter(
				nodes__graph__in=deployed_graphs,
				domain='enterprise-attack',
				revoked=False,
				deprecated=False,
			)
			.values_list('technique_id', flat=True)
	)

	for tid in covered_by_graphs:
		_track_coverage(tid, "Deployed workbench")
	for tid in node_mapped_ids:
		_track_coverage(tid, "Workbench node mapping")

	# 3c) ATT&CK IDs extracted from rules linked to deployed Workbenches.
	workbench_rules = DetectionRule.objects.filter(
		organization=user.organization,
		playbook__in=deployed_graphs,
	).only("title", "description", "raw_content")
	extracted_ids = set()
	for rule in workbench_rules:
		extracted_ids.update(
			_extract_attack_ids_from_text(rule.title, rule.description, rule.raw_content)
		)
	for tid in extracted_ids:
		_track_coverage(tid, "Workbench rule content")

	# 3d) ATT&CK IDs extracted from deployed rules linked to any Workbench.
	deployed_rules = DetectionRule.objects.filter(
		organization=user.organization,
		status__iexact='deployed',
		playbook__isnull=False,
	).only("title", "description", "raw_content")
	deployed_extracted_ids = set()
	for rule in deployed_rules:
		deployed_extracted_ids.update(
			_extract_attack_ids_from_text(rule.title, rule.description, rule.raw_content)
		)
	for tid in deployed_extracted_ids:
		_track_coverage(tid, "Deployed rule content")

	# 3e) Legacy back-compat for old DetectionPlaybook mappings; remove in future cleanup.
	deployed_playbooks = DetectionPlaybook.objects.filter(
		organization=user.organization,
		status=DetectionPlaybook.PlaybookStatus.DEPLOYED,
	)
	covered_by_playbooks = (
		MitreAttackTechnique.objects
			.filter(
				playbooks__in=deployed_playbooks,
				domain='enterprise-attack',
				revoked=False,
				deprecated=False,
			)
			.values_list('technique_id', flat=True)
	)
	for tid in covered_by_playbooks:
		_track_coverage(tid, "Deployed playbook (legacy)")

	# 4) Build parent -> active sub-techniques mapping once.
	parent_children = defaultdict(list)
	for tid in active_technique_ids:
		if "." in tid:
			parent_children[tid.split(".")[0]].append(tid)

	# 5) Build coverage with parent/sub-technique ratio logic.
	techniques_list = []
	processed = set()

	# First pass: add all directly covered techniques.
	for tid, count in direct_coverage.items():
		is_parent = "." not in tid

		if is_parent:
			children = parent_children.get(tid, [])
			if children:
				covered_children = [child for child in children if child in direct_coverage]
				covered_count = len(covered_children)
				total_children = len(children)
				ratio = covered_count / total_children if total_children else 0.0
				if covered_count == 0:
					color = GREEN
					score = 100
					comment = f"Directly mapped with {total_children} sub-techniques"
				elif ratio == 1.0:
					color = GREEN
					score = 100
					comment = f"All {total_children} sub-techniques covered"
				else:
					score = round(ratio * 100)
					color = _ratio_color(ratio)
					comment = f"Directly mapped; {covered_count}/{total_children} sub-techniques covered"
			else:
				color = GREEN
				score = 100
				comment = f"Covered by {count} deployed item(s)"
		else:
			color = GREEN
			score = 100
			comment = f"Covered by {count} deployed item(s)"

		techniques_list.append({
			"techniqueID": tid,
			"color": color,
			"comment": comment,
			"enabled": True,
			"score": score,
			"metadata": [
				{
					"name": "Coverage Source",
					"value": ", ".join(sorted(source_map.get(tid, {"Deployed coverage sources"}))),
				},
				{"name": "Coverage Count", "value": str(count)},
			],
			"links": [],
			"showSubtechniques": True,
		})
		processed.add(tid)

	# Second pass: derive parent indicators for covered sub-techniques.
	for tid in list(direct_coverage.keys()):
		if "." in tid:
			parent_id = tid.split(".")[0]
			if parent_id not in processed:
				children = parent_children.get(parent_id, [])
				covered_children = [c for c in children if c in direct_coverage]
				if not covered_children:
					continue

				covered_count = len(covered_children)
				total_children = len(children)
				ratio = covered_count / total_children if total_children else 0.0
				if ratio == 1.0:
					color = GREEN
					score = 100
					comment = f"All {total_children} sub-techniques covered"
				else:
					score = round(ratio * 100)
					color = _ratio_color(ratio)
					comment = f"{covered_count}/{total_children} sub-techniques covered"

				techniques_list.append({
					"techniqueID": parent_id,
					"color": color,
					"comment": comment,
					"enabled": True,
					"score": score,
					"metadata": [
						{"name": "Coverage Source", "value": "Derived from covered subtechniques"},
						{"name": "Coverage Count", "value": str(score)},
					],
					"links": [],
					"showSubtechniques": True,
				})
				processed.add(parent_id)

	from platform_data.models import PlatformDataVersion
	from platform_data.navigator_sync import resolve_navigator_attack_version
	# The layer must declare a version the embedded Navigator actually serves, or it
	# rejects the layer ("invalid domain") and renders a blank, uncolored matrix with
	# collapsed sub-techniques. Prefer the imported version, but fall back to whatever
	# the Navigator data volume can render.
	attack_version_obj = PlatformDataVersion.objects.filter(framework='enterprise-attack').first()
	preferred_version = attack_version_obj.version if attack_version_obj else None
	attack_version = resolve_navigator_attack_version(preferred_version)

	layer_json = {
		"name": f"{user.organization.name} Detection Coverage",
		"versions": {
			"attack": attack_version,
			"navigator": "5.2.0",
			"layer": "4.5",
		},
		"domain": "enterprise-attack",
		"description": f"Live detection coverage for {user.organization.name} based on deployed workbenches.",
		"sorting": 3,
		"layout": {
			"layout": "side",
			"aggregateFunction": "max",
			"showID": False,
			"showName": True,
			"showAggregateScores": False,
			"countUnscored": False,
			"expandedSubtechniques": "all",
		},
		"hideDisabled": False,
		"selectTechniquesAcrossTactics": True,
		"selectSubtechniquesWithParent": True,
		"techniques": techniques_list,
		"gradient": {
			"colors": ["#fff5b1", "#fdae61", GREEN],
			"minValue": 0,
			"maxValue": 100,
		},
	}

	return JsonResponse(layer_json, json_dumps_params={"ensure_ascii": False})
