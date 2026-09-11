# Empty no-op migration to align migration graph

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pain_points', '0002_add_threaded_comments'),
    ]

    operations = []
