from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from news.models import NewsPost

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds sample news posts for development and testing'

    def handle(self, *args, **options):
        # Get or create an admin user
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@hefaistos.local',
                'is_staff': True,
                'is_superuser': True
            }
        )
        
        if created:
            admin_user.set_password('admin')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('Created admin user'))
        
        # Sample news posts
        sample_posts = [
            {
                'title': 'Platform Update v2.0',
                'content': '🚀 Hefaistos v2.0 is now live! New features include Workbench, ATT&CK Navigator, and MISP integration. Check the changelog for details.',
                'category': 'FEATURE',
                'priority': 'HIGH',
                'is_published': True,
                'is_pinned': True
            },
            {
                'title': 'Scheduled Maintenance',
                'content': '⚠️ System maintenance scheduled for this Saturday 2-4 AM UTC. Expect brief downtime for database upgrades.',
                'category': 'OUTAGE',
                'priority': 'URGENT',
                'is_published': True,
                'is_pinned': True
            },
            {
                'title': '',
                'content': '📢 Weekly threat intel digest now available! Enable in your profile settings to receive curated IoCs and TTPs every Monday.',
                'category': 'ANNOUNCEMENT',
                'priority': 'MEDIUM',
                'is_published': True,
                'is_pinned': False
            },
            {
                'title': 'New AI Models Added',
                'content': '🤖 Added support for GPT-5.2, Gemini 3, and Claude 4.5 models. Update your AI settings to try them out!',
                'category': 'UPDATE',
                'priority': 'MEDIUM',
                'is_published': True,
                'is_pinned': False
            },
            {
                'title': '',
                'content': '🔒 Security patch applied: CVE-2024-12345 addressed. All users should review their detection rules for updated IoCs.',
                'category': 'SECURITY',
                'priority': 'HIGH',
                'is_published': True,
                'is_pinned': False
            },
            {
                'title': 'Playbook Export Feature',
                'content': 'New feature: Export playbooks as YAML for sharing across teams! Find it in the workbench menu.',
                'category': 'FEATURE',
                'priority': 'LOW',
                'is_published': True,
                'is_pinned': False
            },
            {
                'title': '',
                'content': '🔧 Database optimization in progress. Query performance improved by 40%. No action required from users.',
                'category': 'MAINTENANCE',
                'priority': 'LOW',
                'is_published': True,
                'is_pinned': False
            },
            {
                'title': 'Draft: Upcoming RBAC Changes',
                'content': 'Planning to enhance role-based access control. Feedback welcome on the RFC in our wiki.',
                'category': 'ANNOUNCEMENT',
                'priority': 'MEDIUM',
                'is_published': False,  # Draft
                'is_pinned': False
            },
        ]
        
        created_count = 0
        for post_data in sample_posts:
            post, created = NewsPost.objects.get_or_create(
                content=post_data['content'],
                defaults={
                    'title': post_data['title'],
                    'author': admin_user,
                    'category': post_data['category'],
                    'priority': post_data['priority'],
                    'is_published': post_data['is_published'],
                    'is_pinned': post_data['is_pinned']
                }
            )
            
            if created:
                # Set published_at for published posts
                if post.is_published:
                    post.published_at = timezone.now() - timedelta(days=created_count)
                    # Stagger expiration dates
                    post.expires_at = post.published_at + timedelta(days=180)
                    post.save()
                
                created_count += 1
                self.stdout.write(f"Created: {post.title or post.content[:50]}")
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully seeded {created_count} news posts'
            )
        )
