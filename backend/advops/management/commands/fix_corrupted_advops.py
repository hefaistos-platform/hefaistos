"""
Management command to fix corrupted ADVOPS records.
Cleans up priority fields that contain multiple values due to strAIn append bug.

Usage:
    python manage.py fix_corrupted_advops
"""

from django.core.management.base import BaseCommand
from advops.models import ADVOPSReport


class Command(BaseCommand):
    help = 'Fix corrupted ADVOPS records with invalid priority/status values'

    def handle(self, *args, **options):
        self.stdout.write('Scanning for corrupted ADVOPS records...')
        
        valid_priorities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        valid_statuses = ['IDEA', 'RESEARCH', 'DEVELOPMENT', 'APPROVED', 'TESTING', 'DEPLOYED', 'TUNING']
        
        fixed_count = 0
        deleted_count = 0
        
        for report in ADVOPSReport.objects.all():
            needs_fix = False
            
            # Check priority
            if report.priority and '\n' in report.priority:
                self.stdout.write(self.style.WARNING(
                    f'Found corrupted priority in report {report.id}: {report.priority!r}'
                ))
                # Extract first valid priority
                lines = report.priority.split('\n')
                for line in lines:
                    clean = line.strip().upper()
                    if clean in valid_priorities:
                        report.priority = clean
                        needs_fix = True
                        self.stdout.write(f'  Fixed to: {clean}')
                        break
                else:
                    # No valid priority found, set to default
                    report.priority = 'MEDIUM'
                    needs_fix = True
                    self.stdout.write(f'  Set to default: MEDIUM')
            
            # Check status
            if report.status and '\n' in report.status:
                self.stdout.write(self.style.WARNING(
                    f'Found corrupted status in report {report.id}: {report.status!r}'
                ))
                # Extract first valid status
                lines = report.status.split('\n')
                for line in lines:
                    clean = line.strip().upper()
                    if clean in valid_statuses:
                        report.status = clean
                        needs_fix = True
                        self.stdout.write(f'  Fixed to: {clean}')
                        break
                else:
                    # No valid status found, set to default
                    report.status = 'IDEA'
                    needs_fix = True
                    self.stdout.write(f'  Set to default: IDEA')
            
            if needs_fix:
                try:
                    report.save()
                    fixed_count += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'Fixed report {report.id} ({report.hunt_id})'
                    ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f'Failed to fix report {report.id}: {e}'
                    ))
                    # If we can't fix it, consider deleting if it's too corrupted
                    if self.confirm_delete(report):
                        report.delete()
                        deleted_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Fixed {fixed_count} records, deleted {deleted_count} records.'
        ))
    
    def confirm_delete(self, report):
        """Ask user if they want to delete a severely corrupted record"""
        response = input(f'Delete severely corrupted report {report.id} ({report.hunt_id})? [y/N]: ')
        return response.lower() == 'y'
