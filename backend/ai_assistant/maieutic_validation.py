import re
from typing import Dict, List, Tuple

STEP_ALIASES = {
    "hypothesis": "hypothesis",
    "interrogation": "interrogation",
    "robustness": "robustness",
    "playbook": "playbook",
    "review": "review",
}

HINT_LIBRARY: Dict[str, Dict[str, str]] = {
    "hypothesis": {
        "intent": "What is your intent: lateral movement, privilege escalation, or credential access?",
        "capability": "Name the specific behavior, not just the tool (e.g., 'TGS ticket requests for service accounts').",
        "opportunity": "Where does this occur in your environment (DC, workstation, cross-domain)?",
    },
    "interrogation": {
        "data_source": "Which log source captures this behavior (e.g., Event ID 4769, Sysmon)?",
        "mechanism": "What OS or protocol mechanism is used (Kerberos TGS, LSASS API calls)?",
        "lookalike": "What legitimate activity could look similar?",
    },
    "robustness": {
        "pyramid_level": "Pick a level 1-5 and explain one way an attacker could bypass this.",
        "evasion": "What is one likely evasion technique for this detection?",
        "data_dependency": "Is your detection dependent on a specific audit log being enabled?",
    },
    "playbook": {
        "automation": "Add one automated step (enrichment, ticketing, EDR query).",
        "human": "Add one human decision (triage judgment, escalation trigger).",
        "escalation": "Define escalation criteria (severity threshold, trigger conditions).",
    },
    "review": {
        "test_evidence": "Have you tested in a lab or Atomic Red Team?",
        "false_positive": "What false-positive rate is acceptable in week one?",
        "coverage": "Does this fill a gap or duplicate existing coverage?",
    },
}

TOOL_KEYWORDS = [
    "mimikatz",
    "kerberoast",
    "kerberoasting",
    "cobalt",
    "bloodhound",
    "powershell",
    "psexec",
]

INTENT_KEYWORDS = [
    "intent",
    "goal",
    "objective",
    "credential",
    "lateral",
    "privilege",
    "exfil",
    "persistence",
    "execution",
    "collection",
    "discovery",
    "impact",
    "defense evasion",
    "command and control",
    "c2",
]

CAPABILITY_KEYWORDS = [
    "lsass",
    "kerberos",
    "tgs",
    "dcsync",
    "process",
    "registry",
    "powershell",
    "wmi",
    "token",
    "openprocess",
    "readprocessmemory",
    "rpc",
    "service",
    "api",
    "dll",
    "inject",
    "dump",
    "request",
    "access",
]

OPPORTUNITY_KEYWORDS = [
    "domain controller",
    "dc",
    "workstation",
    "endpoint",
    "server",
    "cloud",
    "aws",
    "azure",
    "gcp",
    "tenant",
    "network",
    "on-prem",
    "vpn",
    "remote",
    "host",
    "laptop",
    "environment",
]

DATA_SOURCE_KEYWORDS = [
    "sysmon",
    "event id",
    "eventid",
    "edr",
    "telemetry",
    "logs",
    "log",
    "windows event",
    "audit",
    "dns",
    "proxy",
    "firewall",
    "network",
]

MECHANISM_KEYWORDS = [
    "api",
    "openprocess",
    "readprocessmemory",
    "kerberos",
    "ntlm",
    "lsass",
    "registry",
    "process",
    "wmi",
    "powershell",
    "oauth",
    "token",
    "dll",
    "rpc",
]

LOOKALIKE_KEYWORDS = [
    "legitimate",
    "benign",
    "admin",
    "expected",
    "maintenance",
    "false positive",
    "fp",
    "normal",
    "baseline",
]

EVASION_KEYWORDS = [
    "evade",
    "bypass",
    "tunnel",
    "rename",
    "obfuscate",
    "disable",
    "tamper",
    "masquerade",
    "alternate",
]

DATA_DEPENDENCY_KEYWORDS = [
    "requires",
    "depends",
    "audit",
    "logging",
    "log",
    "sysmon",
    "edr",
    "telemetry",
]

AUTOMATION_KEYWORDS = [
    "automate",
    "automation",
    "soar",
    "api",
    "enrich",
    "ticket",
    "isolate",
    "contain",
    "block",
    "quarantine",
    "disable",
    "alert",
]

HUMAN_KEYWORDS = [
    "analyst",
    "review",
    "triage",
    "investigate",
    "approve",
    "manual",
    "human",
]

ESCALATION_KEYWORDS = [
    "escalate",
    "severity",
    "threshold",
    "criteria",
    "priority",
    "p1",
    "p2",
]

TEST_KEYWORDS = [
    "test",
    "lab",
    "atomic",
    "simulation",
    "red team",
    "emulation",
    "validate",
]

FALSE_POSITIVE_KEYWORDS = [
    "false positive",
    "fp",
    "baseline",
    "fpr",
]

COVERAGE_KEYWORDS = [
    "gap",
    "coverage",
    "overlap",
    "mitre",
    "redundant",
    "fills",
]


def normalize_step(step: str) -> str:
    if not step:
        return "hypothesis"
    return STEP_ALIASES.get(step.strip().lower(), "hypothesis")


def _has_any(text: str, keywords: List[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _has_technique_id(text: str) -> bool:
    return re.search(r"\bT\d{4}(?:\.\d{3})?\b", text, re.IGNORECASE) is not None


def _is_vague_tool_only(text: str) -> bool:
    if not text:
        return False
    words = text.split()
    if len(words) > 3:
        return False
    return any(tool in text for tool in TOOL_KEYWORDS)


def validate_maieutic_input(step: str, text: str) -> Tuple[bool, List[str], List[str]]:
    normalized_step = normalize_step(step)
    content = (text or "").strip().lower()
    missing: List[str] = []

    if normalized_step == "hypothesis":
        if not (_has_any(content, INTENT_KEYWORDS) or _has_technique_id(content)):
            missing.append("intent")
        if not (_has_any(content, CAPABILITY_KEYWORDS) or _has_technique_id(content)):
            missing.append("capability")
        if not _has_any(content, OPPORTUNITY_KEYWORDS):
            missing.append("opportunity")
        if _is_vague_tool_only(content) and "capability" not in missing:
            missing.append("capability")

    elif normalized_step == "interrogation":
        if not _has_any(content, DATA_SOURCE_KEYWORDS):
            missing.append("data_source")
        if not _has_any(content, MECHANISM_KEYWORDS):
            missing.append("mechanism")
        if not _has_any(content, LOOKALIKE_KEYWORDS):
            missing.append("lookalike")

    elif normalized_step == "robustness":
        if not re.search(r"\b[1-5]\b", content):
            missing.append("pyramid_level")
        if not _has_any(content, EVASION_KEYWORDS):
            missing.append("evasion")
        if not _has_any(content, DATA_DEPENDENCY_KEYWORDS):
            missing.append("data_dependency")

    elif normalized_step == "playbook":
        if not _has_any(content, AUTOMATION_KEYWORDS):
            missing.append("automation")
        if not _has_any(content, HUMAN_KEYWORDS):
            missing.append("human")
        if not _has_any(content, ESCALATION_KEYWORDS):
            missing.append("escalation")

    elif normalized_step == "review":
        if not _has_any(content, TEST_KEYWORDS):
            missing.append("test_evidence")
        if not _has_any(content, FALSE_POSITIVE_KEYWORDS):
            missing.append("false_positive")
        if not _has_any(content, COVERAGE_KEYWORDS):
            missing.append("coverage")

    hints = get_hints_for_missing(normalized_step, missing)
    return (len(missing) == 0, missing, hints)


def get_hints_for_missing(step: str, missing: List[str]) -> List[str]:
    normalized_step = normalize_step(step)
    hints = []
    for key in missing:
        hint = HINT_LIBRARY.get(normalized_step, {}).get(key)
        if hint:
            hints.append(hint)
    return hints
