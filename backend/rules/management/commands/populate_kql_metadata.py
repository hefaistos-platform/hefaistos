from django.core.management.base import BaseCommand
from rules.models import KQLTable, KQLField


TABLES = {
    "SecurityEvent": ["Account", "AccountType", "Activity", "Computer", "EventID", "IpAddress"],
    "DeviceNetworkEvents": ["ActionType", "RemoteUrl", "RemotePort", "InitiatingProcessAccountName", "Protocol"],
    "DeviceProcessEvents": ["ActionType", "FileName", "FolderPath", "InitiatingProcessAccountName", "ProcessCommandLine"],
    "IdentityLogonEvents": ["AccountDisplayName", "IPAddress", "DeviceName", "Application", "LogonType"],
}


class Command(BaseCommand):
    help = "Populate KQL tables and fields for autocomplete"

    def handle(self, *args, **options):
        created_tables = 0
        created_fields = 0

        for table_name, fields in TABLES.items():
            table, created = KQLTable.objects.get_or_create(table_name=table_name)
            if created:
                created_tables += 1

            for field_name in fields:
                _, f_created = KQLField.objects.get_or_create(table=table, field_name=field_name)
                if f_created:
                    created_fields += 1

        self.stdout.write(self.style.SUCCESS(
            f"Populated KQL metadata: {created_tables} tables, {created_fields} fields"
        ))
