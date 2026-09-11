import json
import re
from datetime import timedelta

from django.utils import timezone
from jinja2 import Environment, StrictUndefined

from .engine import run_custom_prompt


def _clean_markdown_for_pdf(markdown_text: str) -> str:
    text = markdown_text or ""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text.strip()


def _extract_narrative_sections(markdown_text: str):
    text = re.sub(r"```[\s\S]*?```", "", markdown_text or "")
    sections = []
    current_title = "Narrative"
    current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = re.match(r"^#{1,6}\s*(.+)$", line)
        if heading:
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = heading.group(1).strip() or "Narrative"
            current_lines = []
            continue

        line = re.sub(r"^\s*[-*]\s+", "• ", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\*\*([^*]+)\*\*", r"\1", line)
        line = re.sub(r"\*([^*]+)\*", r"\1", line)
        current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    if not sections:
        fallback = _clean_markdown_for_pdf(markdown_text)
        if fallback:
            return [("Narrative", fallback.splitlines())]
        return [("Narrative", ["No content"])]
    return sections


def build_prompt_context(user, custom_input: str | None = None, custom_context=None) -> dict:
    from ach.models import ACHAnalysis
    from advops.models import ADVOPSReport
    from playbooks.models import PlaybookGraph
    from rules.models import DetectionRule

    org = getattr(user, "organization", None)
    now = timezone.now()
    last_30d = now - timedelta(days=30)

    if org is None:
        stats = {
            "ach": {"total": 0, "created_last_30d": 0},
            "advops": {"total": 0, "created_last_30d": 0},
            "workbench": {"total": 0, "created_last_30d": 0},
            "rules": {
                "total": 0,
                "created_last_30d": 0,
                "active_count": 0,
                "deprecated_count": 0,
            },
        }
    else:
        ach_qs = ACHAnalysis.objects.filter(owner__organization=org)
        advops_qs = ADVOPSReport.objects.filter(organization=org)
        wb_qs = PlaybookGraph.objects.filter(organization=org)
        rules_qs = DetectionRule.objects.filter(organization=org)

        stats = {
            "ach": {
                "total": ach_qs.count(),
                "created_last_30d": ach_qs.filter(created_at__gte=last_30d).count(),
            },
            "advops": {
                "total": advops_qs.count(),
                "created_last_30d": advops_qs.filter(created_at__gte=last_30d).count(),
            },
            "workbench": {
                "total": wb_qs.count(),
                "created_last_30d": wb_qs.filter(created_at__gte=last_30d).count(),
            },
            "rules": {
                "total": rules_qs.count(),
                "created_last_30d": rules_qs.filter(created_at__gte=last_30d).count(),
                "active_count": rules_qs.filter(status__iexact="active").count(),
                "deprecated_count": rules_qs.filter(status__iexact="deprecated").count(),
            },
        }

    parsed_custom_context = {}
    if isinstance(custom_context, dict):
        parsed_custom_context = custom_context
    elif isinstance(custom_context, str) and custom_context.strip():
        try:
            loaded = json.loads(custom_context)
            if isinstance(loaded, dict):
                parsed_custom_context = loaded
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed_custom_context = {}

    return {
        "organization_name": getattr(org, "name", "Unknown Organization"),
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "user_role": getattr(user, "role", ""),
        "user_username": getattr(user, "username", ""),
        "custom_input": (custom_input or "").strip(),
        "custom_context": parsed_custom_context,
        "stats": stats,
    }


def render_prompt_template(prompt_template: str, context: dict) -> str:
    env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=True, lstrip_blocks=True)
    template = env.from_string(prompt_template)
    return template.render(**context).strip()


def execute_prompt_template(user_settings, prompt_template: str, context: dict, prompt_title: str | None = None):
    rendered_prompt = render_prompt_template(prompt_template, context)
    system_prompt = (
        "You are HEFAISTOS MGMT Cave AI Assistant. "
        "Provide concise, actionable management guidance in markdown using headings and bullet points."
    )
    if prompt_title:
        system_prompt = f"{system_prompt} Focus on the selected prompt: {prompt_title}."
    result, provider = run_custom_prompt(
        user_settings=user_settings,
        user_prompt=rendered_prompt,
        system_prompt=system_prompt,
    )
    return rendered_prompt, result, provider


def build_prompt_result_pdf(title: str, markdown_text: str) -> bytes:
    import html
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    safe_title = html.escape(title or "AI Prompt Result")
    generated_at = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    sections = _extract_narrative_sections(markdown_text)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(safe_title, styles["Heading1"]),
        Spacer(1, 0.2 * cm),
        Paragraph(f"Generated: {generated_at}", styles["Italic"]),
        Spacer(1, 0.4 * cm),
    ]

    for section_title, section_lines in sections:
        story.append(Paragraph(html.escape(section_title), styles["Heading2"]))
        story.append(Spacer(1, 0.2 * cm))
        for line in section_lines:
            text = html.escape(line.strip() or " ")
            story.append(Paragraph(text, styles["BodyText"]))
            story.append(Spacer(1, 0.12 * cm))
        story.append(Spacer(1, 0.2 * cm))

    doc.build(story)
    return buf.getvalue()
