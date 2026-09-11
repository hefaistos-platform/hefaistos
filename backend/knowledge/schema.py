import graphene
import json
from graphene_django import DjangoObjectType
from .models import KnowledgeBaseCategory, KnowledgeBaseArticle
from tags.models import TenantTag
from django.utils.text import slugify
from identity.schema import UserType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from core.mcs_logging import emit_security_event, extract_client_ip
from identity.models import CustomUser

# Helper function to check superuser status
def require_superuser(user, request=None, action="knowledge_base_write"):
    """Raises PermissionDenied if user is not a superuser."""
    if not user or user.is_anonymous:
        emit_security_event(
            level="warning",
            logger_name="KnowledgeBaseService",
            message="Anonymous request denied for Knowledge Base operation.",
            event_action=action,
            event_outcome="failure",
            asvs_event_code="AUTHZ-DENY-01",
            event_reason="Authentication required.",
            event_category=["authorization"],
            event_type=["denied", "failure"],
            user_id="anonymous",
            source_ip=extract_client_ip(request),
            request=request,
            http_status_code=401,
        )
        raise PermissionDenied("Authentication required.")
    if not user.is_superuser:
        emit_security_event(
            level="warning",
            logger_name="KnowledgeBaseService",
            message=f"User '{getattr(user, 'username', 'unknown')}' denied Knowledge Base superuser operation.",
            event_action=action,
            event_outcome="failure",
            asvs_event_code="AUTHZ-DENY-01",
            event_reason="Superuser role required.",
            event_category=["authorization"],
            event_type=["denied", "failure"],
            user_id=str(getattr(user, "id", "unknown")),
            user_name=getattr(user, "username", None),
            source_ip=extract_client_ip(request),
            request=request,
            http_status_code=403,
        )
        raise PermissionDenied("Superuser status required to edit Knowledge Base.")


def require_admin_or_superuser(user, request=None, action="knowledge_base_export"):
    """Raises PermissionDenied if user is neither ADMIN role nor superuser."""
    if not user or user.is_anonymous:
        emit_security_event(
            level="warning",
            logger_name="KnowledgeBaseService",
            message="Anonymous request denied for Knowledge Base export operation.",
            event_action=action,
            event_outcome="failure",
            asvs_event_code="AUTHZ-DENY-01",
            event_reason="Authentication required.",
            event_category=["authorization"],
            event_type=["denied", "failure"],
            user_id="anonymous",
            source_ip=extract_client_ip(request),
            request=request,
            http_status_code=401,
        )
        raise PermissionDenied("Authentication required.")
    is_admin_role = getattr(user, "role", None) == CustomUser.Roles.ADMIN
    if not (is_admin_role or user.is_superuser):
        emit_security_event(
            level="warning",
            logger_name="KnowledgeBaseService",
            message=f"User '{getattr(user, 'username', 'unknown')}' denied Knowledge Base export operation.",
            event_action=action,
            event_outcome="failure",
            asvs_event_code="AUTHZ-DENY-01",
            event_reason="Admin or superuser role required.",
            event_category=["authorization"],
            event_type=["denied", "failure"],
            user_id=str(getattr(user, "id", "unknown")),
            user_name=getattr(user, "username", None),
            source_ip=extract_client_ip(request),
            request=request,
            http_status_code=403,
        )
        raise PermissionDenied("Admin or superuser status required to export Knowledge Base.")

# --- TYPES ---

class KnowledgeBaseArticleType(DjangoObjectType):
    author = graphene.Field(UserType)
    tags = graphene.List(graphene.String)

    class Meta:
        model = KnowledgeBaseArticle
        # Keep model fields explicit and provide custom resolvers for author/tags.
        fields = (
            "id",
            "title",
            "content",
            "category",
            "author",
            "organization",
            "created_at",
            "updated_at",
        )

    def resolve_tags(self, info):
        try:
            return list(self.tags.names())
        except Exception:
            return []

class KnowledgeBaseCategoryType(DjangoObjectType):
    # Resolver to get all articles within this category
    articles = graphene.List(KnowledgeBaseArticleType)

    class Meta:
        model = KnowledgeBaseCategory
        fields = ("id", "name", "description", "organization", "articles")

    def resolve_articles(self, info):
        # self is the Category instance.
        # We can access articles via the related_name
        return self.articles.all()


# --- QUERIES ---

class Query(graphene.ObjectType):
    all_kb_categories = graphene.List(
        KnowledgeBaseCategoryType,
        description="Retrieves all Knowledge Base categories (platform-wide, readable by all authenticated users)."
    )
    kb_article = graphene.Field(
        KnowledgeBaseArticleType,
        id=graphene.UUID(required=True),
        description="Retrieves a single Knowledge Base article by its ID (platform-wide)."
    )

    def resolve_all_kb_categories(self, info):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        # Platform-wide: Return all categories (no organization filter)
        return KnowledgeBaseCategory.objects.all()

    def resolve_kb_article(self, info, id):
        user = info.context.user
        if user.is_anonymous:
            raise Exception("Authentication credentials were not provided")

        try:
            # Platform-wide: No organization filter on read
            return KnowledgeBaseArticle.objects.get(pk=id)
        except KnowledgeBaseArticle.DoesNotExist:
            return None


# --- MUTATIONS ---

class CreateKBCategory(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        description = graphene.String()

    category = graphene.Field(KnowledgeBaseCategoryType)

    class Meta:
        description = "Creates a new Knowledge Base category (SuperUser only, platform-wide)."

    @staticmethod
    def mutate(root, info, name, description=None):
        user = info.context.user
        require_superuser(user)

        # Ensure user has an organization
        if not user.organization:
            raise Exception("User must belong to an organization to create Knowledge Base categories")

        # SuperUser creates platform-wide KB (organization can be the first user's org or a dedicated KB org)
        # For now, use the user's organization to avoid NULL org
        category = KnowledgeBaseCategory(
            name=name,
            description=description,
            organization=user.organization
        )
        category.save()
        return CreateKBCategory(category=category)

class CreateKBArticle(graphene.Mutation):
    class Arguments:
        title = graphene.String(required=True)
        content = graphene.String(required=True)
        category_id = graphene.UUID(required=False)
        tags = graphene.List(graphene.String, required=False, description="List of tag names to apply to the article")

    article = graphene.Field(KnowledgeBaseArticleType)

    class Meta:
        description = "Creates a new Knowledge Base article (SuperUser only, platform-wide)."

    @staticmethod
    def mutate(root, info, title, content, category_id=None, tags=None):
        user = info.context.user
        require_superuser(user)

        category = None
        if category_id:
            try:
                # Allow any category (platform-wide)
                category = KnowledgeBaseCategory.objects.get(pk=category_id)
            except KnowledgeBaseCategory.DoesNotExist:
                raise Exception("Category not found")

        article = KnowledgeBaseArticle(
            title=title,
            content=content,
            category=category,
            author=user,
            organization=user.organization  # Platform KB still uses an organization reference
        )
        article.save()

        # Handle tags if provided
        if tags:
            tag_objects = []
            for name in tags:
                cleaned = (name or "").strip()
                if not cleaned:
                    continue
                # Use first organization for platform KB tags (or create tenant-agnostic tags)
                org = user.organization
                tag_obj, _ = TenantTag.objects.get_or_create(
                    name=cleaned,
                    organization=org,
                    defaults={"slug": slugify(cleaned, allow_unicode=True)}
                )
                tag_objects.append(tag_obj)
            article.tags.set(tag_objects)

        return CreateKBArticle(article=article)

class UpdateKBCategory(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)
        name = graphene.String(required=False)
        description = graphene.String(required=False)

    category = graphene.Field(KnowledgeBaseCategoryType)

    class Meta:
        description = "Updates a Knowledge Base category (SuperUser only)."

    @staticmethod
    def mutate(root, info, id, name=None, description=None):
        user = info.context.user
        require_superuser(user)

        try:
            category = KnowledgeBaseCategory.objects.get(pk=id)
        except KnowledgeBaseCategory.DoesNotExist:
            raise Exception("Category not found")

        if name is not None:
            category.name = name
        if description is not None:
            category.description = description
        category.save()
        return UpdateKBCategory(category=category)

class UpdateKBArticleTags(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)
        tags = graphene.List(graphene.String, required=True)

    article = graphene.Field(KnowledgeBaseArticleType)

    class Meta:
        description = "Sets the tags for a Knowledge Base article (SuperUser only)."

    @staticmethod
    def mutate(root, info, id, tags):
        user = info.context.user
        require_superuser(user)

        try:
            article = KnowledgeBaseArticle.objects.get(pk=id)
        except KnowledgeBaseArticle.DoesNotExist:
            raise Exception("Article not found")

        # Normalize names and build TenantTag objects
        normalized = []
        for name in tags or []:
            cleaned = (name or "").strip()
            if not cleaned:
                continue
            # Use article's organization for tagging
            org = article.organization
            tag_obj, _ = TenantTag.objects.get_or_create(
                name=cleaned,
                organization=org,
                defaults={"slug": slugify(cleaned, allow_unicode=True)}
            )
            normalized.append(tag_obj)

        # Replace the set
        article.tags.set(normalized)
        return UpdateKBArticleTags(article=article)

class UpdateKBArticle(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)
        title = graphene.String()
        content = graphene.String()
        category_id = graphene.UUID()

    article = graphene.Field(KnowledgeBaseArticleType)

    class Meta:
        description = "Updates an existing Knowledge Base article (SuperUser only)."

    @staticmethod
    def mutate(root, info, id, **kwargs):
        user = info.context.user
        require_superuser(user)

        try:
            # Platform-wide: No organization filter
            article = KnowledgeBaseArticle.objects.get(pk=id)
        except KnowledgeBaseArticle.DoesNotExist:
            raise Exception("Article not found")

        # Handle category update separately
        if 'category_id' in kwargs:
            category_id = kwargs.pop('category_id')
            if category_id:
                try:
                    category = KnowledgeBaseCategory.objects.get(pk=category_id)
                    article.category = category
                except KnowledgeBaseCategory.DoesNotExist:
                    raise Exception("Category not found")
            else:
                article.category = None # Allow un-setting the category

        # Update all other simple fields
        for field, value in kwargs.items():
            setattr(article, field, value)

        article.save()
        return UpdateKBArticle(article=article)

class DeleteKBArticle(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    ok = graphene.Boolean()

    class Meta:
        description = "Deletes a Knowledge Base article (SuperUser only)."

    @staticmethod
    def mutate(root, info, id):
        user = info.context.user
        require_superuser(user)

        try:
            article = KnowledgeBaseArticle.objects.get(pk=id)
        except KnowledgeBaseArticle.DoesNotExist:
            raise Exception("Article not found")

        article.delete()
        return DeleteKBArticle(ok=True)

class DeleteKBCategory(graphene.Mutation):
    class Arguments:
        id = graphene.UUID(required=True)

    ok = graphene.Boolean()

    class Meta:
        description = "Deletes a Knowledge Base category (SuperUser only). Articles will not be deleted and their category will be set to NULL."

    @staticmethod
    def mutate(root, info, id):
        user = info.context.user
        require_superuser(user)

        try:
            category = KnowledgeBaseCategory.objects.get(pk=id)
        except KnowledgeBaseCategory.DoesNotExist:
            raise Exception("Category not found")

        # Due to on_delete=SET_NULL on KnowledgeBaseArticle.category, deleting the
        # category will automatically null out the FK for related articles.
        category.delete()
        return DeleteKBCategory(ok=True)


class ExportKBArticles(graphene.Mutation):
    ok = graphene.Boolean()
    filename = graphene.String()
    payload_json = graphene.String()

    class Meta:
        description = "Exports Knowledge Base categories/articles as JSON (Admin or SuperUser)."

    @staticmethod
    def mutate(root, info):
        user = info.context.user
        require_admin_or_superuser(user, request=info.context, action="knowledge_base_export")

        categories = KnowledgeBaseCategory.objects.all().prefetch_related("articles__tags")
        uncategorized_articles = KnowledgeBaseArticle.objects.filter(category__isnull=True).prefetch_related("tags")

        payload = {
            "version": 1,
            "exported_at": timezone.now().isoformat(),
            "categories": [],
            "uncategorized_articles": [],
        }

        for category in categories:
            payload["categories"].append(
                {
                    "name": category.name,
                    "description": category.description,
                    "articles": [
                        {
                            "title": article.title,
                            "content": article.content,
                            "tags": list(article.tags.names()),
                        }
                        for article in category.articles.all()
                    ],
                }
            )

        payload["uncategorized_articles"] = [
            {
                "title": article.title,
                "content": article.content,
                "tags": list(article.tags.names()),
            }
            for article in uncategorized_articles
        ]

        filename = f"knowledge-base-export-{timezone.now().strftime('%Y%m%d-%H%M%S')}.json"
        emit_security_event(
            level="informational",
            logger_name="KnowledgeBaseService",
            message=(
                f"Knowledge Base export completed by user '{getattr(user, 'username', 'unknown')}'. "
                f"Exported categories={len(payload['categories'])}, uncategorized_articles={len(payload['uncategorized_articles'])}."
            ),
            event_action="knowledge_base_export",
            event_outcome="success",
            asvs_event_code="BIZLOGIC-DATA-EXPORT-01",
            event_reason="Knowledge Base export generated successfully.",
            event_category=["authorization"],
            event_type=["end", "success"],
            user_id=str(getattr(user, "id", "unknown")),
            user_name=getattr(user, "username", None),
            source_ip=extract_client_ip(info.context),
            request=info.context,
            http_status_code=200,
            asvs_details={
                "authorization": {
                    "resource_type": "knowledge_base",
                    "required_permission": "role:ADMIN_OR_SUPERUSER",
                }
            },
            extra_context={
                "categories": len(payload["categories"]),
                "uncategorized_articles": len(payload["uncategorized_articles"]),
            },
        )
        return ExportKBArticles(ok=True, filename=filename, payload_json=json.dumps(payload, ensure_ascii=False, indent=2))


class ImportKBArticles(graphene.Mutation):
    ok = graphene.Boolean()
    categories_created = graphene.Int()
    categories_updated = graphene.Int()
    articles_created = graphene.Int()
    articles_updated = graphene.Int()

    class Arguments:
        payload_json = graphene.String(required=True)

    class Meta:
        description = "Imports Knowledge Base categories/articles from exported JSON (SuperUser only)."

    @staticmethod
    def mutate(root, info, payload_json):
        user = info.context.user
        require_superuser(user, request=info.context, action="knowledge_base_import")

        if not user.organization:
            emit_security_event(
                level="warning",
                logger_name="KnowledgeBaseService",
                message=(
                    f"Knowledge Base import denied for user '{getattr(user, 'username', 'unknown')}' "
                    "because no organization is assigned."
                ),
                event_action="knowledge_base_import",
                event_outcome="failure",
                asvs_event_code="BIZLOGIC-FAIL-WORKFLOW-01",
                event_reason="User must belong to an organization to import Knowledge Base content.",
                event_category=["authorization"],
                event_type=["denied", "failure"],
                user_id=str(getattr(user, "id", "unknown")),
                user_name=getattr(user, "username", None),
                source_ip=extract_client_ip(info.context),
                request=info.context,
                http_status_code=400,
            )
            raise Exception("User must belong to an organization to import Knowledge Base content")

        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            emit_security_event(
                level="warning",
                logger_name="KnowledgeBaseService",
                message=f"Knowledge Base import failed for user '{getattr(user, 'username', 'unknown')}' due to invalid JSON payload.",
                event_action="knowledge_base_import",
                event_outcome="failure",
                asvs_event_code="BIZLOGIC-FAIL-WORKFLOW-01",
                event_reason="Invalid JSON payload.",
                event_category=["authorization"],
                event_type=["end", "failure"],
                user_id=str(getattr(user, "id", "unknown")),
                user_name=getattr(user, "username", None),
                source_ip=extract_client_ip(info.context),
                request=info.context,
                http_status_code=400,
            )
            raise Exception("Invalid JSON payload")

        if not isinstance(payload, dict):
            raise Exception("Invalid payload format")

        categories_data = payload.get("categories", [])
        uncategorized_data = payload.get("uncategorized_articles", [])
        if not isinstance(categories_data, list) or not isinstance(uncategorized_data, list):
            raise Exception("Invalid payload format for categories or uncategorized_articles")

        categories_created = 0
        categories_updated = 0
        articles_created = 0
        articles_updated = 0

        try:
            with transaction.atomic():
                for category_data in categories_data:
                    if not isinstance(category_data, dict):
                        continue
                    name = (category_data.get("name") or "").strip()
                    if not name:
                        continue
                    description = category_data.get("description")

                    category, category_created = KnowledgeBaseCategory.objects.get_or_create(
                        name=name,
                        organization=user.organization,
                        defaults={"description": description},
                    )
                    if category_created:
                        categories_created += 1
                    else:
                        if category.description != description:
                            category.description = description
                            category.save(update_fields=["description"])
                            categories_updated += 1

                    for article_data in category_data.get("articles", []) or []:
                        if not isinstance(article_data, dict):
                            continue
                        title = (article_data.get("title") or "").strip()
                        if not title:
                            continue
                        content = article_data.get("content") or ""

                        article, article_created = KnowledgeBaseArticle.objects.get_or_create(
                            title=title,
                            category=category,
                            organization=user.organization,
                            defaults={"content": content, "author": user},
                        )
                        if article_created:
                            articles_created += 1
                        else:
                            article.content = content
                            article.author = user
                            article.save(update_fields=["content", "author", "updated_at"])
                            articles_updated += 1

                        tag_objects = []
                        for tag_name in article_data.get("tags", []) or []:
                            cleaned = (tag_name or "").strip()
                            if not cleaned:
                                continue
                            tag_obj, _ = TenantTag.objects.get_or_create(
                                name=cleaned,
                                organization=user.organization,
                                defaults={"slug": slugify(cleaned, allow_unicode=True)},
                            )
                            tag_objects.append(tag_obj)
                        article.tags.set(tag_objects)

                for article_data in uncategorized_data:
                    if not isinstance(article_data, dict):
                        continue
                    title = (article_data.get("title") or "").strip()
                    if not title:
                        continue
                    content = article_data.get("content") or ""

                    article, article_created = KnowledgeBaseArticle.objects.get_or_create(
                        title=title,
                        category=None,
                        organization=user.organization,
                        defaults={"content": content, "author": user},
                    )
                    if article_created:
                        articles_created += 1
                    else:
                        article.content = content
                        article.author = user
                        article.save(update_fields=["content", "author", "updated_at"])
                        articles_updated += 1

                    tag_objects = []
                    for tag_name in article_data.get("tags", []) or []:
                        cleaned = (tag_name or "").strip()
                        if not cleaned:
                            continue
                        tag_obj, _ = TenantTag.objects.get_or_create(
                            name=cleaned,
                            organization=user.organization,
                            defaults={"slug": slugify(cleaned, allow_unicode=True)},
                        )
                        tag_objects.append(tag_obj)
                    article.tags.set(tag_objects)
        except Exception as exc:
            emit_security_event(
                level="error",
                logger_name="KnowledgeBaseService",
                message=f"Knowledge Base import failed for user '{getattr(user, 'username', 'unknown')}'.",
                event_action="knowledge_base_import",
                event_outcome="failure",
                asvs_event_code="BIZLOGIC-FAIL-WORKFLOW-01",
                event_reason=str(exc),
                event_category=["authorization"],
                event_type=["end", "failure"],
                user_id=str(getattr(user, "id", "unknown")),
                user_name=getattr(user, "username", None),
                source_ip=extract_client_ip(info.context),
                request=info.context,
                http_status_code=500,
            )
            raise

        emit_security_event(
            level="informational",
            logger_name="KnowledgeBaseService",
            message=(
                f"Knowledge Base import completed by user '{getattr(user, 'username', 'unknown')}'. "
                f"categories_created={categories_created}, categories_updated={categories_updated}, "
                f"articles_created={articles_created}, articles_updated={articles_updated}."
            ),
            event_action="knowledge_base_import",
            event_outcome="success",
            asvs_event_code="BIZLOGIC-DATA-IMPORT-01",
            event_reason="Knowledge Base import completed successfully.",
            event_category=["authorization"],
            event_type=["end", "success"],
            user_id=str(getattr(user, "id", "unknown")),
            user_name=getattr(user, "username", None),
            source_ip=extract_client_ip(info.context),
            request=info.context,
            http_status_code=200,
            asvs_details={
                "authorization": {
                    "resource_type": "knowledge_base",
                    "required_permission": "role:SUPERUSER",
                }
            },
            extra_context={
                "categories_created": categories_created,
                "categories_updated": categories_updated,
                "articles_created": articles_created,
                "articles_updated": articles_updated,
            },
        )

        return ImportKBArticles(
            ok=True,
            categories_created=categories_created,
            categories_updated=categories_updated,
            articles_created=articles_created,
            articles_updated=articles_updated,
        )

class Mutation(graphene.ObjectType):
    create_kb_category = CreateKBCategory.Field()
    create_kb_article = CreateKBArticle.Field()
    update_kb_article = UpdateKBArticle.Field()
    delete_kb_article = DeleteKBArticle.Field()
    update_kb_category = UpdateKBCategory.Field()
    update_kb_article_tags = UpdateKBArticleTags.Field()
    delete_kb_category = DeleteKBCategory.Field()
    export_kb_articles = ExportKBArticles.Field()
    import_kb_articles = ImportKBArticles.Field()
