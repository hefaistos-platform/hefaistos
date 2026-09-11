"""
Django management command to generate a GraphQL JWT token for the connector_svc user.
Usage: python manage.py generate_connector_token
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from graphql_jwt.shortcuts import get_token

User = get_user_model()

class Command(BaseCommand):
    help = 'Generate a GraphQL JWT token for the connector_svc user'

    def handle(self, *args, **options):
        try:
            user = User.objects.get(username='connector_svc')
            access_token = get_token(user)
            
            self.stdout.write(self.style.SUCCESS('\n' + '='*70))
            self.stdout.write(self.style.SUCCESS('JWT Token Generated Successfully'))
            self.stdout.write(self.style.SUCCESS('='*70))
            self.stdout.write(f"\nUsername: {user.username}")
            self.stdout.write(f"Organization: {user.organization.name}")
            self.stdout.write(f"\nAccess Token:")
            self.stdout.write(self.style.WARNING(access_token))
            self.stdout.write(self.style.SUCCESS('\n' + '='*70))
            self.stdout.write("\nSet this as HEFAISTOS_API_TOKEN in your environment:")
            self.stdout.write(f"export HEFAISTOS_API_TOKEN={access_token}")
            self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
            
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('Error: connector_svc user does not exist'))
            self.stdout.write('Create it first by running: python manage.py migrate')
            return
