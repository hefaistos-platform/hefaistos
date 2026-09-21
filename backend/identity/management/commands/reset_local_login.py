"""
Django management command to re-enable local (username/password) login.

Use this as a recovery tool when OIDC is misconfigured and you are locked out
of the web interface:

    python manage.py reset_local_login
    python manage.py reset_local_login --add-username myuser
    python manage.py reset_local_login --org-id <uuid>

The command enables the break-glass flag so local users can log in again.
Optionally adds a username to the break-glass allow-list.
"""
from django.core.management.base import BaseCommand

from identity.models import AuthProviderSettings


class Command(BaseCommand):
    help = (
        'Re-enable local (username/password) login as a recovery tool when OIDC '
        'is misconfigured and you are locked out of the web interface.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--add-username',
            dest='add_username',
            metavar='USERNAME',
            help=(
                'Add this username to the break-glass allow-list '
                '(comma-separated list stored in the settings).'
            ),
        )
        parser.add_argument(
            '--org-id',
            dest='org_id',
            metavar='ORG_UUID',
            help=(
                'Target a specific organisation by UUID. '
                'Defaults to the global (platform-wide) auth settings.'
            ),
        )

    def handle(self, *args, **options):
        org_id = options.get('org_id')
        add_username = options.get('add_username')

        if org_id:
            settings_obj = AuthProviderSettings.resolve_for_org_id(org_id)
            if settings_obj is None:
                self.stderr.write(
                    self.style.ERROR(f'No organisation found with id={org_id}')
                )
                return
            scope_label = f'organisation {org_id}'
        else:
            settings_obj = AuthProviderSettings.get_solo()
            scope_label = 'global (platform-wide)'

        changed_fields = []

        if not settings_obj.allow_local_breakglass:
            settings_obj.allow_local_breakglass = True
            changed_fields.append('allow_local_breakglass')
            self.stdout.write(self.style.SUCCESS('  allow_local_breakglass → True'))
        else:
            self.stdout.write('  allow_local_breakglass is already True — no change needed.')

        if add_username:
            username_lower = add_username.strip().lower()
            existing = [u.lower() for u in settings_obj.breakglass_usernames_list() if u]
            if username_lower not in existing:
                existing.append(username_lower)
                settings_obj.breakglass_usernames = ','.join(existing)
                changed_fields.append('breakglass_usernames')
                self.stdout.write(
                    self.style.SUCCESS(f"  Added '{username_lower}' to break-glass allow-list.")
                )
            else:
                self.stdout.write(
                    f"  '{username_lower}' is already in the break-glass allow-list — no change."
                )

        if changed_fields:
            settings_obj.save(update_fields=changed_fields)
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nLocal login re-enabled for {scope_label} auth settings.'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    '\nNo changes were necessary — local login was already enabled.'
                )
            )

        allow_list = ', '.join(settings_obj.breakglass_usernames_list())
        if not allow_list:
            allow_list = '(empty — all superusers may use local login)'
        self.stdout.write('\nCurrent break-glass allow-list: ' + allow_list)
        self.stdout.write(
            'OIDC enabled:   ' + str(settings_obj.enable_oidc)
        )
        self.stdout.write(
            'Entra enabled:  ' + str(settings_obj.enable_entra)
        )
