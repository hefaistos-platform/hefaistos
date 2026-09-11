import uuid
from django.db import models
from organizations.models import Organization
from identity.models import CustomUser
from taggit.managers import TaggableManager

class KnowledgeBaseCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="kb_categories"
    )

    class Meta:
        verbose_name = "Knowledge Base Category"
        verbose_name_plural = "Knowledge Base Categories"
        unique_together = ('organization', 'name') # Category names are unique per org
        ordering = ['name']

    def __str__(self):
        return self.name

class KnowledgeBaseArticle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)

    # We use TextField for Markdown. A rich text editor (e.g., CKEditor)
    # could be a future enhancement.
    content = models.TextField(help_text="Article content in Markdown format.")

    author = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="kb_articles"
    )
    category = models.ForeignKey(
        KnowledgeBaseCategory,
        on_delete=models.SET_NULL, # If category is deleted, don't delete article
        null=True,
        blank=True,
        related_name="articles"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="kb_articles"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Per-article tags (tenant-scoped via custom tag model in tags app)
    tags = TaggableManager(through='tags.TaggedKBArticle', blank=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title
