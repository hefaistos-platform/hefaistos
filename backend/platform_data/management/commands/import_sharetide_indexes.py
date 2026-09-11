"""
Management command: import_sharetide_indexes

Populates (or refreshes) the ShareTideIndexEntry table with vocabulary entries
aligned with the ShareTide schema specifications:
  https://github.com/OpenTideHQ/ShareTide/tree/main/Schemas/Indexes

The command ships with a comprehensive set of built-in defaults that mirror the
known ShareTide vocabulary.  When the ``--remote`` flag is passed it will also
attempt to fetch the latest index files directly from GitHub and merge any new
entries found there.

Usage::

    # Populate/refresh from built-in defaults (no internet required)
    python manage.py import_sharetide_indexes

    # Attempt to fetch latest entries from GitHub as well
    python manage.py import_sharetide_indexes --remote

    # Clear all existing entries before importing
    python manage.py import_sharetide_indexes --clear
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

from django.core.management.base import BaseCommand
from django.db import transaction

logger = logging.getLogger(__name__)


def _path_to_uri(path: str) -> str:
    """Convert a filesystem path to a proper file:// URI (cross-platform)."""
    return Path(path).as_uri()

# ---------------------------------------------------------------------------
# Built-in ShareTide vocabulary (aligned with ShareTide schema v2.0 / v2.1)
# ---------------------------------------------------------------------------

SHARETIDE_BASE_URL = (
    "https://raw.githubusercontent.com/OpenTideHQ/ShareTide/main/Schemas/Indexes"
)

# Each entry: (value, description, sort_order)
_BUILT_IN: Dict[str, List[tuple]] = {
    # --- BDR ---
    "bdr_criticality": [
        ("Emergency", "Immediate threat to critical business operations", 0),
        ("Severe", "Serious risk requiring urgent attention", 1),
        ("High", "High-impact security or compliance event", 2),
        ("Medium", "Moderate risk warranting timely response", 3),
        ("Low", "Low-impact event requiring standard follow-up", 4),
        ("Baseline - Negligible", "Informational; negligible operational impact", 5),
        ("Baseline - Minor", "Minor deviation from baseline; low risk", 6),
    ],
    "bdr_domains": [
        ("Enterprise", "Traditional corporate IT environment", 0),
        ("Public Cloud", "AWS, Azure, GCP and similar public cloud platforms", 1),
        ("Private Cloud", "On-premises virtualised or private cloud infrastructure", 2),
        ("Mobile", "Mobile devices and mobile application platforms", 3),
        ("SaaS", "Software-as-a-Service applications and platforms", 4),
        ("Networking", "Network infrastructure, firewalls, switches, routers", 5),
        ("OSINT", "Open-source intelligence and external threat sources", 6),
        ("Embedded", "Embedded systems and firmware", 7),
        ("IoT", "Internet of Things devices and ecosystems", 8),
        ("Industrial", "Operational technology (OT) and industrial control systems", 9),
    ],
    "bdr_targets": [
        ("Critical Documents", "Sensitive business or classified documents", 0),
        ("Personal Information", "Personally identifiable information (PII)", 1),
        ("Identity Services", "Authentication, authorisation, and directory services", 2),
        ("Workstations", "End-user workstations and laptops", 3),
        ("Servers", "Application, database, and infrastructure servers", 4),
        ("Network Infrastructure", "Routers, switches, firewalls, and network appliances", 5),
        ("Cloud Resources", "Cloud compute, storage, and managed services", 6),
        ("Email", "Email systems and messaging platforms", 7),
        ("Applications", "Business and web applications", 8),
        ("Databases", "Relational and non-relational database systems", 9),
        ("Directory", "Active Directory, LDAP, and identity stores", 10),
        ("Credentials", "User and service account credentials", 11),
        ("Mobile Devices", "Smartphones and tablets", 12),
        ("IoT Devices", "Internet of Things endpoints", 13),
        ("Industrial Systems", "SCADA, PLCs, and industrial control systems", 14),
    ],
    "bdr_platforms": [
        ("Windows", "Microsoft Windows operating systems", 0),
        ("Linux", "Linux-based operating systems", 1),
        ("macOS", "Apple macOS operating systems", 2),
        ("AWS", "Amazon Web Services cloud platform", 3),
        ("Azure", "Microsoft Azure cloud platform", 4),
        ("GCP", "Google Cloud Platform", 5),
        ("Active Directory", "Microsoft Active Directory on-premises", 6),
        ("Azure AD", "Microsoft Azure Active Directory / Entra ID", 7),
        ("Office 365", "Microsoft 365 / Office 365 suite", 8),
        ("Google Workspace", "Google Workspace (formerly G Suite)", 9),
        ("Kubernetes", "Kubernetes container orchestration", 10),
        ("Docker", "Docker container runtime", 11),
        ("VMware", "VMware virtualisation platform", 12),
        ("Network Devices", "Generic network devices (routers, switches, firewalls)", 13),
        ("Mobile", "Mobile device platforms (iOS, Android)", 14),
    ],
    # --- MDR ---
    "mdr_alert_severities": [
        ("Critical", "Immediately actionable; potential ongoing compromise", 0),
        ("High", "High-confidence alert requiring prompt investigation", 1),
        ("Medium", "Moderate confidence; further investigation required", 2),
        ("Low", "Low confidence or low-impact; review during normal operations", 3),
        ("Informational", "Informational only; no immediate action required", 4),
    ],
    "mdr_responders": [
        ("CSIRC", "Computer Security Incident Response Centre", 0),
        ("CATCH", "Cyber Attack and Threat Containment & Hunting team", 1),
        ("MARTI", "Managed Advanced Response and Threat Intelligence", 2),
        ("S1-SA", "Tier-1 Security Analyst", 3),
    ],
    "mdr_platforms": [
        ("Sentinel", "Microsoft Azure Sentinel / Microsoft Sentinel (KQL)", 0),
        ("Splunk", "Splunk Enterprise / Splunk Cloud (SPL)", 1),
        ("Elastic", "Elastic Security (EQL / Lucene)", 2),
        ("Sigma", "Generic SIEM-agnostic Sigma rules", 3),
        ("QRadar", "IBM QRadar SIEM", 4),
        ("CrowdStrike", "CrowdStrike Falcon platform", 5),
        ("Wazuh", "Wazuh open-source SIEM/EDR", 6),
        ("Chronicle", "Google Chronicle SIEM", 7),
        ("Sumo Logic", "Sumo Logic cloud SIEM", 8),
    ],
    # --- DOM ---
    "dom_priorities": [
        ("Critical", "Highest priority; business-critical detection gap", 0),
        ("High", "High priority; significant detection gap", 1),
        ("Medium", "Medium priority; moderate detection gap", 2),
        ("Low", "Low priority; minor detection gap", 3),
    ],
    "dom_methodologies": [
        ("Artifacts", "Detection based on forensic artefacts or indicators of compromise", 0),
        ("Pattern Matching", "Rule-based matching on known patterns or signatures", 1),
        ("Event Search", "Targeted search across event logs for specific event types", 2),
        ("Statistical", "Statistical baseline deviation or frequency-based detection", 3),
        ("Behavioural", "Detection of anomalous or malicious behavioural patterns", 4),
        ("Anomaly", "Detection of deviations from established baselines", 5),
        ("Machine Learning", "ML-model-based detection of malicious activity", 6),
        ("Heuristic", "Rule-of-thumb heuristics applied to suspicious indicators", 7),
        ("Threat Intelligence", "Detection driven by curated threat intelligence indicators", 8),
    ],
    "dom_log_sources": [
        ("siem::Windows Security Events", "Windows Security event log (channel Security)", 0),
        ("siem::Sysmon", "Sysinternals Sysmon process and network telemetry", 1),
        ("siem::Network Logs", "Network flow, DNS, firewall and proxy logs", 2),
        ("siem::Process Events", "Generic process creation and execution events", 3),
        ("siem::File Events", "File system creation, modification and deletion events", 4),
        ("siem::Registry Events", "Windows Registry read and write events", 5),
        ("siem::Authentication Events", "Authentication, logon and Kerberos/NTLM events", 6),
        ("siem::Script Execution Events", "PowerShell, WMI and COM script execution events", 7),
        ("siem::Generic SIEM", "Generic SIEM event source with no specific category", 8),
        ("mde::Microsoft Defender XDR", "Microsoft Defender for Endpoint / XDR advanced hunting", 9),
        ("splunk::Splunk", "Splunk Enterprise or Splunk Cloud index", 10),
        ("wazuh::Wazuh SIEM", "Wazuh open-source SIEM and EDR platform", 11),
        ("elastic::Elastic SIEM", "Elastic Security (EQL/Lucene) index", 12),
        ("qradar::QRadar SIEM", "IBM QRadar SIEM AQL data source", 13),
    ],
    "dom_statuses": [
        ("Active", "Detection objective is actively monitored", 0),
        ("Draft", "Detection objective under development", 1),
        ("Deprecated", "Detection objective is no longer maintained", 2),
        ("Review", "Detection objective under periodic review", 3),
    ],
    # --- TVM ---
    "tvm_threat_levels": [
        ("Critical", "Nation-state or highly sophisticated threat actor", 0),
        ("High", "Advanced threat actor with targeted capability", 1),
        ("Medium", "Commodity threat actor using known toolkits", 2),
        ("Low", "Opportunistic or script-kiddie level threat", 3),
    ],
    "tvm_leverage": [
        # STRIDE threat categories + infrastructure-specific extensions
        ("Spoofing", "Adversary impersonates a legitimate entity or resource (STRIDE)", 0),
        ("Tampering", "Adversary modifies data, code, or system state (STRIDE)", 1),
        ("Repudiation", "Adversary denies performing an action or covers tracks (STRIDE)", 2),
        ("Information Disclosure", "Adversary exposes sensitive information (STRIDE)", 3),
        ("Denial of Service", "Adversary disrupts availability of a resource (STRIDE)", 4),
        ("Elevation of Privilege", "Adversary gains higher permissions than intended (STRIDE)", 5),
        ("Infrastructure Compromise", "Adversary subverts or takes control of underlying infrastructure", 6),
        ("Dwelling", "Adversary maintains persistent, undetected presence in the environment", 7),
    ],
    "tvm_impact": [
        ("Nuisance", "Low-impact disruption causing inconvenience without significant harm", 0),
        ("Impairement", "Partial degradation of business or operational capability", 1),
        ("Data Breach", "Unauthorised access to or exfiltration of sensitive data", 2),
        ("IP Loss", "Loss or theft of intellectual property or trade secrets", 3),
        ("Reputational Damages", "Harm to organisational reputation or public trust", 4),
        ("Identity Theft", "Theft or misuse of personal or organisational identity credentials", 5),
        ("Monetary Loss", "Direct or indirect financial loss to the organisation", 6),
        ("Lose Capabilities", "Loss of operational, technical, or mission capabilities", 7),
    ],
    "tvm_viability": [
        ("Almost no chance", "Attack is theoretical with negligible probability of success", 0),
        ("Very Unlikely", "Attack faces significant barriers; success is rare", 1),
        ("Unlikely", "Attack is possible but unlikely under most conditions", 2),
        ("Roughly even chance", "Attack success depends on specific configuration or defences", 3),
        ("Likely", "Attack has a better-than-even probability of succeeding", 4),
        ("Very Likely", "Attack is expected to succeed in most target environments", 5),
        ("Almost certain", "Attack is straightforward and almost always succeeds", 6),
        ("Environment dependent", "Success depends entirely on target-specific conditions", 7),
    ],
    "tvm_surface": [
        # Threat Surface vocabulary using strict domain::Entity formatting
        ("host::Account", "Local host account credentials and permission scope", 0),
        ("cloud::Account", "Cloud service account, IAM role, or managed identity", 1),
        ("host::User", "Local interactive user session and profile context", 2),
        ("cloud::User", "Cloud identity, federated user, or directory account", 3),
        ("host::Hostname", "Physical or virtual endpoint device identity", 4),
        ("network::IP Address", "Network-accessible host identified by IP address or range", 5),
        ("host::Process", "Process running on an endpoint host", 6),
        ("host::Command Line", "Command-line execution context and argument string", 7),
    ],
}


class Command(BaseCommand):
    help = "Populate (or refresh) ShareTide vocabulary index entries in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--remote",
            action="store_true",
            default=False,
            help="Attempt to fetch index updates from GitHub in addition to built-in defaults.",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Delete all existing entries before importing.",
        )
        parser.add_argument(
            "--import-schema-toml",
            dest="schema_toml_path",
            default=None,
            metavar="PATH",
            help=(
                "Import additional vocabulary entries from an OpenTide "
                "'Configurations/schema.toml' file into the database.  Entries "
                "whose name already exists in the database are skipped (no-op).  "
                "This option can be combined with the built-in import."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from platform_data.models import ShareTideIndexEntry

        if options["clear"]:
            count = ShareTideIndexEntry.objects.all().delete()[0]
            self.stdout.write(self.style.WARNING(f"Cleared {count} existing entries."))

        created = updated = 0

        for category, entries in _BUILT_IN.items():
            for entry in entries:
                value, description, sort_order = entry
                obj, was_created = ShareTideIndexEntry.objects.update_or_create(
                    category=category,
                    value=value,
                    defaults={
                        "description": description,
                        "sort_order": sort_order,
                        "source_url": f"{SHARETIDE_BASE_URL}/{category}.json",
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Built-in import complete: {created} created, {updated} updated."
            )
        )

        if options["remote"]:
            self._import_remote(ShareTideIndexEntry)

        if options["schema_toml_path"]:
            self._import_schema_toml(ShareTideIndexEntry, options["schema_toml_path"])

    def _import_remote(self, model):
        """Attempt to fetch and merge entries from GitHub (best-effort)."""
        try:
            import requests  # type: ignore
        except ImportError:
            self.stdout.write(
                self.style.WARNING("'requests' not available – skipping remote fetch.")
            )
            return

        import json

        remote_created = remote_updated = 0

        for category in _BUILT_IN.keys():
            url = f"{SHARETIDE_BASE_URL}/{category}.json"
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
                # Expected format: list of strings or list of {"value": ..., "description": ...}
                entries = data if isinstance(data, list) else data.get("entries", [])
                for idx, item in enumerate(entries):
                    if isinstance(item, str):
                        value, description = item, ""
                    elif isinstance(item, dict):
                        value = item.get("value") or item.get("name") or str(item)
                        description = item.get("description", "")
                    else:
                        continue
                    obj, was_created = model.objects.update_or_create(
                        category=category,
                        value=value,
                        defaults={
                            "description": description,
                            "sort_order": idx,
                            "source_url": url,
                        },
                    )
                    if was_created:
                        remote_created += 1
                    else:
                        remote_updated += 1
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f"Remote fetch failed for {category}: {exc}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Remote import complete: {remote_created} created, {remote_updated} updated."
            )
        )

    def _import_schema_toml(self, model, path: str) -> None:
        """Import vocabulary from an OpenTide ``Configurations/schema.toml`` file."""
        from playbooks.utils.schema_toml import read_vocab_from_schema_toml

        self.stdout.write(f"Importing vocabulary from schema.toml: {path}")
        try:
            vocab = read_vocab_from_schema_toml(path)
        except (FileNotFoundError, ValueError) as exc:
            self.stdout.write(self.style.ERROR(f"Failed to read schema.toml: {exc}"))
            return

        toml_created = toml_skipped = 0

        for category, entries in vocab.items():
            for idx, entry in enumerate(entries):
                value = entry.get('name', '').strip()
                if not value:
                    continue
                description = entry.get('description', '')
                _, was_created = model.objects.get_or_create(
                    category=category,
                    value=value,
                    defaults={
                        "description": description,
                        "sort_order": 1000 + idx,  # place after built-ins
                        "source_url": _path_to_uri(path),
                    },
                )
                if was_created:
                    toml_created += 1
                else:
                    toml_skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"schema.toml import complete: {toml_created} created, "
                f"{toml_skipped} already present (skipped)."
            )
        )
