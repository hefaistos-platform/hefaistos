from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0007_inittide_require_deployed'),
    ]

    operations = [
        migrations.AddField(
            model_name='playbookcommithistory',
            name='committed_file_paths',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='All relative paths committed in this push (TVM, DOM, MDR)',
            ),
        ),
        migrations.AlterField(
            model_name='playbookcommithistory',
            name='file_path',
            field=models.CharField(
                help_text='Primary relative path within the InitTide repository (MDR file)',
                max_length=512,
            ),
        ),
    ]
