from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0031_alter_platformcredential_options_and_more'),
        ('waiting_room', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='waitingcase',
            name='source_type',
            field=models.CharField(choices=[('MANUAL', 'Manual'), ('MISP', 'MISP'), ('API', 'API')], default='MANUAL', max_length=16),
        ),
        migrations.CreateModel(
            name='WaitingCaseInboundReference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(max_length=64)),
                ('external_id', models.CharField(max_length=255)),
                ('severity', models.CharField(blank=True, default='', max_length=16)),
                ('artifacts', models.JSONField(blank=True, default=list)),
                ('detected_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='waiting_case_inbound_references', to='organizations.organization')),
                ('waiting_case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inbound_references', to='waiting_room.waitingcase')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='waitingcaseinboundreference',
            constraint=models.UniqueConstraint(fields=('organization', 'source', 'external_id'), name='waiting_case_inbound_ref_org_source_external_unique'),
        ),
    ]
