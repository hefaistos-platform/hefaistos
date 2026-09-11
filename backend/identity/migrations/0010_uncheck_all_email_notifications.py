from django.db import migrations, models


def uncheck_all_email_notifications(apps, schema_editor):
    CustomUser = apps.get_model('identity', 'CustomUser')
    CustomUser.objects.update(
        email_notify_review_approved=False,
        email_notify_system_message=False,
        email_notify_chat_message=False,
        email_notify_workbench_edited=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0009_mfaauditevent_mfaloginchallenge_usermfasettings_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='email_notify_review_approved',
            field=models.BooleanField(default=False, help_text='Email me when my review is approved'),
        ),
        migrations.AlterField(
            model_name='customuser',
            name='email_notify_workbench_edited',
            field=models.BooleanField(default=False, help_text='Email me when someone edits my workbench'),
        ),
        migrations.RunPython(uncheck_all_email_notifications, migrations.RunPython.noop),
    ]
