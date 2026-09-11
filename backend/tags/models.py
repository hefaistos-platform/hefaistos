from django.db import models
from taggit.models import TagBase, ItemBase
from organizations.models import Organization
from django.utils.text import slugify

class TenantTag(TagBase):
    # Override name and slug to remove the global unique constraint added by TagBase.
    # We enforce uniqueness per-organization via `unique_together` below.
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, allow_unicode=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="tags"
    )

    class Meta:
        # Enforce that a tag name is unique within an organization
        unique_together = ("name", "organization")
        verbose_name = "Tag"
        verbose_name_plural = "Tags"

class TaggedPlaybook(ItemBase):
    tag = models.ForeignKey(
        TenantTag,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_items",
    )
    content_object = models.ForeignKey(
        'playbooks.DetectionPlaybook',
        on_delete=models.CASCADE,
    )

    class Meta:
        # Enforce that a tag can only be applied once to a playbook
        unique_together = ("content_object", "tag")


class TaggedKBArticle(ItemBase):
    tag = models.ForeignKey(
        TenantTag,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_items",
    )
    content_object = models.ForeignKey(
        'knowledge.KnowledgeBaseArticle',
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ("content_object", "tag")


class TaggedGraph(ItemBase):
    tag = models.ForeignKey(
        TenantTag,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_items",
    )
    content_object = models.ForeignKey(
        'playbooks.PlaybookGraph',
        on_delete=models.CASCADE,
    )

    class Meta:
        unique_together = ("content_object", "tag")
