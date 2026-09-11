# Empty no-op migration

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('pain_points', '0003_add_threaded_comments'),
    ]
    
    operations = []

