from django.db import migrations


PROMPTS = [
    {
        "title": "Gap Analysis Advisor",
        "description": "Identify current coverage gaps and the most important remediation priorities.",
        "category": "ANALYTICS",
        "required_role": "REVIEWER",
        "order": 10,
        "prompt_template": """
You are a management cyber defense advisor.
Analyze coverage posture for {{ organization_name }} using the stats below and produce:
1) top 5 gaps,
2) likely risk impact,
3) prioritized remediation plan for the next 30 days.

Stats:
- ACH total: {{ stats.ach.total }} (last 30d: {{ stats.ach.created_last_30d }})
- AdvOps total: {{ stats.advops.total }} (last 30d: {{ stats.advops.created_last_30d }})
- Workbench total: {{ stats.workbench.total }} (last 30d: {{ stats.workbench.created_last_30d }})
- Rules total: {{ stats.rules.total }} (active: {{ stats.rules.active_count }}, deprecated: {{ stats.rules.deprecated_count }})

Additional context: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Robustness Optimizer",
        "description": "Recommend practical actions to improve detection quality and durability.",
        "category": "ANALYTICS",
        "required_role": "REVIEWER",
        "order": 20,
        "prompt_template": """
Provide a robustness optimization report for {{ organization_name }}.
Focus on quality of detection engineering lifecycle and recommend:
- immediate fixes (this week),
- medium-term actions (this month),
- strategic improvements (this quarter).

Use this context:
- Rules active: {{ stats.rules.active_count }}
- Rules deprecated: {{ stats.rules.deprecated_count }}
- Workbench total: {{ stats.workbench.total }}
- AdvOps total: {{ stats.advops.total }}

User note: {{ custom_input or "none" }}
""",
    },
    {
        "title": "SOAR Readiness Check",
        "description": "Assess operational readiness for response automation and orchestration.",
        "category": "OPERATIONS",
        "required_role": "REVIEWER",
        "order": 30,
        "prompt_template": """
Perform a SOAR readiness check for {{ organization_name }}.
Deliver:
1) readiness score (0-100),
2) blockers,
3) phased roadmap to improve orchestration maturity.

Inputs:
- AdvOps total: {{ stats.advops.total }}
- Workbench total: {{ stats.workbench.total }}
- Rules active: {{ stats.rules.active_count }}
- Recent activity (30d): ACH {{ stats.ach.created_last_30d }}, AdvOps {{ stats.advops.created_last_30d }}, Workbench {{ stats.workbench.created_last_30d }}, Rules {{ stats.rules.created_last_30d }}

Extra requirements: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Technique Prioritization",
        "description": "Prioritize ATT&CK-focused engineering backlog based on likely value.",
        "category": "THREAT_HUNTING",
        "required_role": "REVIEWER",
        "order": 40,
        "prompt_template": """
Prioritize detection engineering focus areas for {{ organization_name }}.
Create a ranked backlog with rationale and expected outcome.
Use a clear table-like markdown output.

Current context:
- ACH analyses: {{ stats.ach.total }}
- Active rules: {{ stats.rules.active_count }}
- Deprecated rules: {{ stats.rules.deprecated_count }}
- Workbenches: {{ stats.workbench.total }}

Context from manager: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Analyst Performance Insights",
        "description": "Generate leadership-ready insights on team workflow and throughput.",
        "category": "ANALYTICS",
        "required_role": "ADMIN",
        "order": 50,
        "prompt_template": """
Generate analyst performance insights for {{ organization_name }} leadership.
Provide findings, caveats, and recommendations without exposing personal data.

Use aggregate indicators:
- ACH total / last 30d: {{ stats.ach.total }} / {{ stats.ach.created_last_30d }}
- AdvOps total / last 30d: {{ stats.advops.total }} / {{ stats.advops.created_last_30d }}
- Workbench total / last 30d: {{ stats.workbench.total }} / {{ stats.workbench.created_last_30d }}
- Rules total / last 30d: {{ stats.rules.total }} / {{ stats.rules.created_last_30d }}

Executive focus: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Detection Debt Snapshot",
        "description": "Summarize technical debt in detection content and suggest remediation.",
        "category": "ANALYTICS",
        "required_role": "REVIEWER",
        "order": 60,
        "prompt_template": """
Create a detection debt snapshot for {{ organization_name }}.
Highlight likely debt indicators and propose an actionable debt reduction plan.

Indicators:
- Active rules: {{ stats.rules.active_count }}
- Deprecated rules: {{ stats.rules.deprecated_count }}
- Workbench total: {{ stats.workbench.total }}

Special notes: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Threat Hunt Campaign Planner",
        "description": "Plan a 2-week threat hunting campaign with measurable outcomes.",
        "category": "THREAT_HUNTING",
        "required_role": "REVIEWER",
        "order": 70,
        "prompt_template": """
Design a 2-week threat hunt campaign for {{ organization_name }}.
Return campaign objective, daily milestones, required telemetry, and success metrics.

Operational context:
- AdvOps hunts: {{ stats.advops.total }}
- Recent AdvOps (30d): {{ stats.advops.created_last_30d }}
- ACH analyses: {{ stats.ach.total }}

Campaign constraints: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Coverage Drift Detector",
        "description": "Identify warning signs of detection coverage drift and mitigation actions.",
        "category": "OPERATIONS",
        "required_role": "REVIEWER",
        "order": 80,
        "prompt_template": """
Detect coverage drift signals for {{ organization_name }} and provide mitigation actions.
Use the platform metrics to infer potential drift risk and confidence level.

Metrics:
- Rules total: {{ stats.rules.total }}
- Rules deprecated: {{ stats.rules.deprecated_count }}
- Workbench recent 30d: {{ stats.workbench.created_last_30d }}
- ACH recent 30d: {{ stats.ach.created_last_30d }}

Operator comment: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Compliance Evidence Draft",
        "description": "Draft compliance-oriented evidence narrative from current management metrics.",
        "category": "COMPLIANCE",
        "required_role": "ADMIN",
        "order": 90,
        "prompt_template": """
Draft a compliance evidence summary for {{ organization_name }}.
Target audience: security audit and governance stakeholders.
Tone: factual, concise, evidence-driven.

Evidence inputs:
- ACH: {{ stats.ach.total }} total ({{ stats.ach.created_last_30d }} in last 30d)
- AdvOps: {{ stats.advops.total }} total ({{ stats.advops.created_last_30d }} in last 30d)
- Workbench: {{ stats.workbench.total }} total ({{ stats.workbench.created_last_30d }} in last 30d)
- Rules: {{ stats.rules.total }} total, {{ stats.rules.active_count }} active, {{ stats.rules.deprecated_count }} deprecated

Control framework context: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Incident Readiness Brief",
        "description": "Prepare a short brief on detection and response readiness posture.",
        "category": "OPERATIONS",
        "required_role": "REVIEWER",
        "order": 100,
        "prompt_template": """
Produce an incident readiness brief for {{ organization_name }}.
Include strengths, weaknesses, and top 3 investments.

Current snapshot:
- Active rules: {{ stats.rules.active_count }}
- Workbench count: {{ stats.workbench.total }}
- AdvOps count: {{ stats.advops.total }}

Scenario assumptions: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Executive Risk Narrative",
        "description": "Translate technical telemetry posture into executive-level risk narrative.",
        "category": "COMPLIANCE",
        "required_role": "ADMIN",
        "order": 110,
        "prompt_template": """
Create an executive risk narrative for {{ organization_name }}.
Audience: C-level stakeholders.
Output should include key risks, confidence, and next decisions.

Use:
- Rules active/deprecated: {{ stats.rules.active_count }}/{{ stats.rules.deprecated_count }}
- Workbench total: {{ stats.workbench.total }}
- AdvOps total: {{ stats.advops.total }}
- ACH total: {{ stats.ach.total }}

Board context: {{ custom_input or "none" }}
""",
    },
    {
        "title": "Quarterly Program Review",
        "description": "Generate a quarterly security detection program review with recommendations.",
        "category": "ANALYTICS",
        "required_role": "ADMIN",
        "order": 120,
        "prompt_template": """
Generate a quarterly detection program review for {{ organization_name }}.
Include:
- notable progress,
- key bottlenecks,
- quantified priorities for next quarter.

Current data:
- ACH total / 30d: {{ stats.ach.total }} / {{ stats.ach.created_last_30d }}
- AdvOps total / 30d: {{ stats.advops.total }} / {{ stats.advops.created_last_30d }}
- Workbench total / 30d: {{ stats.workbench.total }} / {{ stats.workbench.created_last_30d }}
- Rules total / active / deprecated: {{ stats.rules.total }} / {{ stats.rules.active_count }} / {{ stats.rules.deprecated_count }}

Program focus area: {{ custom_input or "none" }}
""",
    },
]


def seed_prompts(apps, schema_editor):
    AIPrompt = apps.get_model("mgmt_reports", "AIPrompt")
    for item in PROMPTS:
        AIPrompt.objects.update_or_create(
            title=item["title"],
            defaults={
                "description": item["description"],
                "category": item["category"],
                "prompt_template": item["prompt_template"].strip(),
                "is_system": True,
                "is_active": True,
                "required_role": item["required_role"],
                "order": item["order"],
            },
        )


def unseed_prompts(apps, schema_editor):
    AIPrompt = apps.get_model("mgmt_reports", "AIPrompt")
    titles = [item["title"] for item in PROMPTS]
    AIPrompt.objects.filter(title__in=titles, is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("mgmt_reports", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_prompts, unseed_prompts),
    ]
