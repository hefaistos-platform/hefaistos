from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('playbooks', '0039_playbookgraph_downstream_correlation_requirements'),
        ('organizations', '0016_opentidehefpublishjob_push_flags'),
    ]

    operations = [
        migrations.DeleteModel(
            name='InitTideConfiguration',
        ),
        migrations.DeleteModel(
            name='OpenTideCommitJob',
        ),
        migrations.DeleteModel(
            name='PlaybookCommitHistory',
        ),
    ]
