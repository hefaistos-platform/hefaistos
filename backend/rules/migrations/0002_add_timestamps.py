from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('rules', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='detectionrule',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='detectionrule',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
