# Generated migration for threaded comments support

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pain_points', '0002_add_threaded_comments'),
    ]

    operations = [
        migrations.AddField(
            model_name='painpointcomment',
            name='parent_comment',
            field=models.ForeignKey(
                blank=True,
                help_text='Parent comment if this is a reply to another comment',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='replies',
                to='pain_points.painpointcomment',
            ),
        ),
        migrations.AddField(
            model_name='painpointcomment',
            name='is_response_to_question',
            field=models.BooleanField(
                default=False,
                help_text='True if this comment is answering a question from admin',
            ),
        ),
        migrations.AddIndex(
            model_name='painpointcomment',
            index=models.Index(fields=['parent_comment'], name='pain_points_parent_c_idx'),
        ),
        migrations.AddIndex(
            model_name='painpointcomment',
            index=models.Index(fields=['pain_point', 'parent_comment'], name='pain_points_pp_pc_idx'),
        ),
        migrations.AlterModelOptions(
            name='painpointcomment',
            options={'ordering': ['created_at']},
        ),
    ]
