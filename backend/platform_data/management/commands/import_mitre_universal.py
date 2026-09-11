import os
import io
import requests
import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from platform_data.models import (
    MitreAttackTechnique, MitreDetectionStrategy, MitreAnalytic, MitreDomain,
    PlatformDataVersion,
)
from platform_data.navigator_sync import sync_navigator_data

MITRE_BASE_URL = "https://attack.mitre.org/docs/attack-excel-files"

# Expected column names per sheet (used for early validation).
# Values are sets of accepted aliases so the import stays resilient to minor
# MITRE spelling changes across versions.
_REQUIRED_COLS = {
    'techniques': {'ID', 'STIX ID', 'name', 'url'},
    'detectionstrategies': {'ID', 'STIX ID', 'name', 'url'},
    'analytics': {'STIX ID', 'name', 'url'},
    'relationships': {'source ref', 'target ref', 'mapping type'},
}


class Command(BaseCommand):
    help = 'Imports MITRE ATT&CK data (all versions, Strategy-Based)'

    def add_arguments(self, parser):
        parser.add_argument('--mitre-version', type=str, default='19.1')
        parser.add_argument('--mode', type=str, choices=['remote', 'local'], default='remote')
        parser.add_argument('--dir', type=str)

    def get_excel_file(self, mode, version, domain, local_dir=None):
        filename = f"{domain}-v{version}.xlsx"
        if mode == 'remote':
            url = f"{MITRE_BASE_URL}/v{version}/{domain}/{filename}"
            self.stdout.write(f"Downloading: {url}...")
            try:
                r = requests.get(url, timeout=120)
                r.raise_for_status()
                return pd.ExcelFile(io.BytesIO(r.content))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"  Download failed: {exc}"))
                return None
        elif mode == 'local':
            if not local_dir:
                return None
            path = os.path.join(local_dir, filename)
            if os.path.exists(path):
                self.stdout.write(f"Reading: {path}")
                return pd.ExcelFile(path)
            self.stderr.write(self.style.ERROR(f"  File not found: {path}"))
            return None

    def _validate_columns(self, sheet_name, df):
        """Warn when expected columns are absent; returns True when safe to proceed."""
        expected = _REQUIRED_COLS.get(sheet_name)
        if not expected:
            return True
        actual = set(df.columns)
        missing = expected - actual
        if missing:
            self.stderr.write(
                self.style.WARNING(
                    f"  [WARN] Sheet '{sheet_name}' is missing expected columns: "
                    f"{sorted(missing)}. Import may produce empty values. "
                    "Check that --mitre-version matches the downloaded file."
                )
            )
        return True  # warn but continue; MITRE sometimes renames columns between releases

    @transaction.atomic
    def handle(self, *args, **options):
        version = options['mitre_version']
        if version.startswith('v'):
            version = version[1:]

        domains = [
            (MitreDomain.ENTERPRISE, 'enterprise-attack'),
            (MitreDomain.ICS, 'ics-attack'),
            (MitreDomain.MOBILE, 'mobile-attack'),
        ]

        for db_domain, url_name in domains:
            self.stdout.write(self.style.WARNING(f"--- Processing {url_name} ---"))
            xls = self.get_excel_file(options['mode'], version, url_name, options['dir'])
            if not xls:
                continue

            # 1. TECHNIQUES
            if 'techniques' in xls.sheet_names:
                self.stdout.write("Importing Techniques...")
                df = pd.read_excel(xls, 'techniques')
                self._validate_columns('techniques', df)
                count = revoked_count = deprecated_count = 0
                for _, row in df.iterrows():
                    tech_id = row.get('ID')
                    if not tech_id or pd.isna(tech_id):
                        continue

                    # Normalise boolean columns – MITRE uses TRUE/FALSE strings or
                    # actual booleans depending on the Excel version.
                    def _bool(val):
                        if pd.isna(val):
                            return False
                        if isinstance(val, bool):
                            return val
                        return str(val).strip().upper() in ('TRUE', '1', 'YES')

                    is_revoked = _bool(row.get('revoked'))
                    is_deprecated = _bool(row.get('deprecated'))

                    # Tactic column name varies; try common aliases in priority order.
                    tactic_raw = (
                        row.get('tactics')
                        or row.get('tactic')
                        or row.get('Tactics')
                        or row.get('Tactic')
                        or ''
                    )
                    tactic_val = '' if pd.isna(tactic_raw) else str(tactic_raw).strip()

                    _, created = MitreAttackTechnique.objects.update_or_create(
                        technique_id=tech_id,
                        domain=db_domain,
                        defaults={
                            'stix_id': row.get('STIX ID'),
                            'name': row.get('name') or '',
                            'url': row.get('url') or '',
                            'tactic': tactic_val,
                            'revoked': is_revoked,
                            'deprecated': is_deprecated,
                        },
                    )
                    count += 1
                    if is_revoked:
                        revoked_count += 1
                    if is_deprecated:
                        deprecated_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f" - Imported {count} techniques "
                        f"({revoked_count} revoked, {deprecated_count} deprecated)."
                    )
                )

            # 2. DETECTION STRATEGIES
            if 'detectionstrategies' in xls.sheet_names:
                self.stdout.write("Importing Detection Strategies...")
                df = pd.read_excel(xls, 'detectionstrategies')
                self._validate_columns('detectionstrategies', df)
                count = 0
                for _, row in df.iterrows():
                    stix_id = row.get('STIX ID')
                    if not stix_id or pd.isna(stix_id):
                        continue
                    MitreDetectionStrategy.objects.update_or_create(
                        stix_id=stix_id,
                        defaults={
                            'def_id': row.get('ID'),
                            'name': row.get('name') or '',
                            'url': row.get('url') or '',
                            'domain': db_domain,
                        },
                    )
                    count += 1
                self.stdout.write(f" - Imported {count} Strategies.")

            # 3. ANALYTICS (Linking to Strategy via URL)
            if 'analytics' in xls.sheet_names:
                self.stdout.write("Importing Analytics and linking to Strategies...")
                df = pd.read_excel(xls, 'analytics')
                self._validate_columns('analytics', df)
                strat_map = {
                    s.def_id: s
                    for s in MitreDetectionStrategy.objects.filter(domain=db_domain)
                    if s.def_id
                }
                count = 0
                for _, row in df.iterrows():
                    stix_id = row.get('STIX ID')
                    if not stix_id or pd.isna(stix_id):
                        continue

                    # Parse URL: https://attack.mitre.org/detectionstrategies/DET0897#AN2030
                    url = str(row.get('url', ''))
                    strat_obj = None
                    if 'detectionstrategies/' in url:
                        try:
                            det_part = url.split('detectionstrategies/')[1]
                            det_id = det_part.split('#')[0]
                            strat_obj = strat_map.get(det_id)
                        except Exception:
                            pass

                    MitreAnalytic.objects.update_or_create(
                        stix_id=stix_id,
                        defaults={
                            'name': row.get('name') or '',
                            'description': row.get('description') or '',
                            'domain': db_domain,
                            'detection_strategy': strat_obj,
                        },
                    )
                    count += 1
                self.stdout.write(f" - Imported {count} Analytics.")

            # 4. RELATIONSHIPS (Strategy -> Technique)
            if 'relationships' in xls.sheet_names:
                self.stdout.write("Linking Strategies to Techniques...")
                df = pd.read_excel(xls, 'relationships')
                self._validate_columns('relationships', df)

                tech_map = {
                    t.stix_id: t
                    for t in MitreAttackTechnique.objects.filter(domain=db_domain)
                    if t.stix_id
                }
                strat_map = {
                    s.stix_id: s
                    for s in MitreDetectionStrategy.objects.filter(domain=db_domain)
                }
                links = 0
                for _, row in df.iterrows():
                    src = str(row.get('source ref', '') or '').strip()
                    tgt = str(row.get('target ref', '') or '').strip()
                    mapping = str(row.get('mapping type', '') or '').strip()

                    if mapping == 'detects':
                        if src in strat_map and tgt in tech_map:
                            strat_map[src].techniques.add(tech_map[tgt])
                            links += 1

                self.stdout.write(self.style.SUCCESS(f" - Linked {links} relationships."))

            # Record successfully loaded version for this domain
            PlatformDataVersion.objects.update_or_create(
                framework=db_domain,
                defaults={'version': version},
            )

        try:
            sync_navigator_data(version)
            self.stdout.write(self.style.SUCCESS("Navigator data synchronized to /navigator-data."))
        except Exception as exc:
            # The framework data committed successfully above, but without a matching
            # Navigator bundle the Coverage Map will reject the layer and render blank.
            # Surface this loudly (and fail the command) instead of swallowing it.
            self.stderr.write(self.style.ERROR(
                f"[ERROR] Navigator data sync FAILED for v{version}: {exc}\n"
                f"        ATT&CK framework data imported OK, but the embedded Navigator has no v{version} "
                f"bundle, so the Coverage Map will not color coverage until this is resolved.\n"
                f"        Re-run the import or sync once /navigator-data is writable and reachable."
            ))
            raise CommandError(f"Navigator data sync failed for v{version}: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Universal Import Complete."))
