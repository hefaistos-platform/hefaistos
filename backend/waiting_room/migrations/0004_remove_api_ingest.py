from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('waiting_room', '0003_mispimportledger'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='waitingcaseinboundreference',
            name='waiting_case_inbound_ref_org_source_external_unique',
        ),
        migrations.DeleteModel(
            name='WaitingCaseInboundReference',
        ),
    ]
