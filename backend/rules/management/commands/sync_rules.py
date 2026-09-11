import os
import git
import yaml
from django.core.management.base import BaseCommand, CommandError
from organizations.models import Organization
from rules.models import RuleRepository, DetectionRule

class Command(BaseCommand):
    help = 'Clones or pulls updates for all rule repositories of a specific organization.'

    def add_arguments(self, parser):
        parser.add_argument('organization_id', type=str, help='The UUID of the Organization to sync repositories for.')

    def handle(self, *args, **options):
        org_id = options['organization_id']
        try:
            organization = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            raise CommandError(f'Organization with ID "{org_id}" does not exist.')

        self.stdout.write(f'Starting sync for organization: {organization.name}...')

        repos_to_sync = RuleRepository.objects.filter(organization=organization)
        if not repos_to_sync.exists():
            self.stdout.write(self.style.WARNING(f'No repositories found for organization "{organization.name}".'))
            return

        for repo in repos_to_sync:
            self.stdout.write(f'-- Syncing repository: {repo.name}')
            
            # Define a tenant-specific local path for the repository
            repo_path = os.path.join('/tmp/rule_repos', str(organization.id), repo.name)

            try:
                # --- This is the Git logic from Day 11 ---
                if os.path.exists(repo_path):
                    self.stdout.write(f'    Repository exists at {repo_path}, pulling latest changes...')
                    git_repo = git.Repo(repo_path)
                    origin = git_repo.remotes.origin
                    origin.pull()
                    self.stdout.write(self.style.SUCCESS('    Successfully pulled latest changes.'))
                else:
                    self.stdout.write(f'    Cloning repository from {repo.git_url} to {repo_path}...')
                    git.Repo.clone_from(repo.git_url, repo_path)
                    self.stdout.write(self.style.SUCCESS('    Successfully cloned repository.'))

                # --- This is the Parsing logic from Day 12 ---
                self.stdout.write('    Parsing rule files...')
                rule_count = 0
                for root, _, files in os.walk(repo_path):
                    for file in files:
                        if file.endswith('.yml'):
                            file_path = os.path.join(root, file)
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    raw_content = f.read()
                                    # Use yaml.safe_load to avoid security risks
                                    rule_data = yaml.safe_load(raw_content)

                                    # Skip if it's not a valid Sigma rule with a title and id
                                    if not isinstance(rule_data, dict) or not all(k in rule_data for k in ['title', 'id']):
                                        continue

                                    # Create or update the rule, ensuring it's linked to the correct organization
                                    DetectionRule.objects.update_or_create(
                                        sigma_id=rule_data['id'],
                                        organization=organization, # CRITICAL: Enforce tenancy
                                        defaults={
                                            'title': rule_data['title'],
                                            'status': rule_data.get('status'),
                                            'description': rule_data.get('description'),
                                            'author': rule_data.get('author'),
                                            'raw_content': raw_content,
                                            'repository': repo,
                                        }
                                    )
                                    rule_count += 1
                            except yaml.YAMLError as e:
                                self.stderr.write(self.style.WARNING(f'    Could not parse {file_path}: {e}'))
                            except Exception as e:
                                self.stderr.write(self.style.ERROR(f'    Error processing file {file_path}: {e}'))

                self.stdout.write(f'    Processed {rule_count} rules.')
                
            # --- These are the original except blocks for the Git logic ---
            except git.exc.GitCommandError as e:
                self.stderr.write(self.style.ERROR(f'    Git command failed for {repo.name}: {e}'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'    An unexpected error occurred for {repo.name}: {e}'))

        self.stdout.write(self.style.SUCCESS(f'Finished sync for organization: {organization.name}'))
