# Merge migration to resolve circular dependencies

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pain_points', '0002_add_threaded_comments_consolidated'),
        ('pain_points', '0002_rename_pain_points_organiza_idx_pain_points_organiz_715dd4_idx_and_more'),
    ]
    
    operations = []
