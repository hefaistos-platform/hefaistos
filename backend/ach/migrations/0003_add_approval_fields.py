from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    # Depend directly on 0001 to match existing database state
    dependencies = [
        ('ach', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='achanalysis',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='achanalysis',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_ach_analyses', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='achanalysis',
            name='status',
            field=models.CharField(choices=[('RESEARCH', 'Research'), ('FINISHED', 'Finished'), ('APPROVED', 'Approved')], default='RESEARCH', max_length=20),
        ),
    ]
