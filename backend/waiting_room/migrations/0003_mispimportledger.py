import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0034_mispinstance_auto_pull'),
        ('waiting_room', '0002_waitingcaseinboundreference_and_api_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='MISPImportLedger',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('misp_event_id', models.CharField(max_length=64)),
                ('misp_event_uuid', models.CharField(blank=True, default='', max_length=64)),
                ('imported_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='misp_import_ledger_entries', to='organizations.organization')),
                ('misp_instance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='misp_import_ledger_entries', to='organizations.mispinstance')),
                ('waiting_case', models.ForeignKey(blank=True, help_text='The WaitingCase created at import time, if any. May become null if that case is later deleted.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ledger_entries', to='waiting_room.waitingcase')),
            ],
            options={
                'ordering': ['-imported_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='mispimportledger',
            constraint=models.UniqueConstraint(fields=('misp_instance', 'misp_event_id'), name='misp_import_ledger_instance_event_unique'),
        ),
    ]
