# News & Announcements Feature

## Overview

Platform-wide news and announcements system with rich categories, markdown support, and auto-expiration.

## Features

✅ **Global Announcements**: Platform-wide news visible to all users  
✅ **Rich Categories**: 6 categories with emoji icons (Feature, Outage, Maintenance, Security, Update, Announcement)  
✅ **Markdown Support**: Formatted content up to 500 characters  
✅ **Auto-Expiration**: Posts expire after 180 days by default  
✅ **Priority Levels**: LOW, MEDIUM, HIGH, URGENT  
✅ **Pinning**: Important posts stay at the top  
✅ **Read Tracking**: Unread count badge for users  
✅ **Draft Mode**: Create and edit before publishing  
✅ **RabbitMQ Integration**: Publishes `news.published` events  

## Database Models

### NewsPost
- `id`: UUID primary key
- `title`: Optional title (max 200 chars)
- `content`: Markdown content (max 500 chars) **required**
- `author`: Foreign key to User
- `priority`: LOW | MEDIUM | HIGH | URGENT
- `category`: UPDATE | OUTAGE | FEATURE | MAINTENANCE | ANNOUNCEMENT | SECURITY
- `is_published`: Boolean (draft vs published)
- `is_pinned`: Boolean (pin to top)
- `published_at`: Auto-set when first published
- `expires_at`: Auto-set to +180 days from publish
- `created_at`, `updated_at`: Timestamps

### UserNewsRead
- `id`: UUID primary key
- `user`: Foreign key to User
- `news_post`: Foreign key to NewsPost
- `read_at`: Timestamp
- **Unique together**: (user, news_post)

## GraphQL API

### Queries

```graphql
# Get all news (with filters)
allNews(
  limit: Int = 50
  offset: Int = 0
  category: String
  includeExpired: Boolean = false
): [NewsPostType!]!

# Get single news post
newsPost(id: UUID!): NewsPostType

# Unread count for current user
unreadNewsCount: Int!

# Get pinned posts only
pinnedNews: [NewsPostType!]!
```

### Mutations (Admin Only)

```graphql
# Create news post (starts as draft)
createNewsPost(
  title: String
  content: String!
  priority: String = "MEDIUM"
  category: String = "ANNOUNCEMENT"
  isPinned: Boolean = false
  expiresAt: DateTime
): CreateNewsPostPayload!

# Update existing post
updateNewsPost(
  id: UUID!
  title: String
  content: String
  priority: String
  category: String
  isPinned: Boolean
  expiresAt: DateTime
): UpdateNewsPostPayload!

# Publish post (triggers RabbitMQ event)
publishNewsPost(id: UUID!): PublishNewsPostPayload!

# Unpublish post
unpublishNewsPost(id: UUID!): UnpublishNewsPostPayload!

# Delete post
deleteNewsPost(id: UUID!): DeleteNewsPostPayload!
```

### Mutations (All Users)

```graphql
# Mark single post as read
markNewsAsRead(newsId: UUID!): MarkNewsAsReadPayload!

# Mark all posts as read
markAllNewsAsRead: MarkAllNewsAsReadPayload!
```

## Setup Instructions

### 1. Create Migrations

```bash
cd /opt/hefaistos/backend
python manage.py makemigrations news
python manage.py migrate
```

### 2. Seed Sample Data (Optional)

```bash
python manage.py seed_news
```

This creates:
- Admin user (if not exists)
- 8 sample news posts (7 published, 1 draft)
- Mix of categories and priorities

### 3. Verify GraphQL Schema

```bash
# Start backend
docker compose up -d backend

# Test query
curl -X POST https://localhost:8443/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"query": "{ allNews(limit: 5) { id title content category priority } }"}'
```

## RabbitMQ Integration

When a news post is published, the system emits:

**Event**: `news.published`  
**Routing Key**: `news.published`  
**Payload**:
```json
{
  "event": "news.published",
  "news_id": "uuid",
  "title": "string",
  "content": "string",
  "priority": "HIGH",
  "category": "FEATURE",
  "author_username": "admin",
  "published_at": "2025-12-23T12:00:00Z"
}
```

### Optional: Email Digest Connector

You can create a connector to listen for `news.published` events and send email notifications:

```python
class NewsEmailConnector(BaseConnector):
    def get_queue_bindings(self):
        return [('news_email_queue', 'news.published')]
    
    def process_message(self, routing_key, payload):
        # Send email to subscribed users
        send_news_email(payload)
```

## Admin Interface

Accessible at `/admin/news/newspost/`

**List View**:
- Title/Content preview
- Category, Priority
- Published status, Pinned status
- Published/Expiration dates
- Author

**Edit View**:
- Content section (title, content, category, priority)
- Publishing section (published, pinned, dates)
- Metadata (ID, author, timestamps)

## Frontend Integration (Phase 2)

### Required Components

1. **NewsIcon** (`frontend/src/components/NewsIcon.tsx`)
   - Bell/newspaper icon in header
   - Badge showing unread count
   - Polls `unreadNewsCount` every 30s

2. **NewsModal** (`frontend/src/components/NewsModal.tsx`)
   - Opens on NewsIcon click
   - Lists news posts (pinned first)
   - Each item: emoji category, title, content, timestamp
   - "Mark all as read" button
   - Filter by category dropdown

3. **Admin News Page** (`frontend/src/pages/AdminNewsPage.tsx`)
   - Route: `/news` (admin-only)
   - CRUD table for news posts
   - Create/Edit modal with form
   - Character counter for content
   - Publish/Unpublish toggle
   - Preview pane

### GraphQL Queries (Frontend)

```typescript
const GET_NEWS = gql`
  query GetNews($limit: Int, $offset: Int) {
    allNews(limit: $limit, offset: $offset) {
      id
      title
      content
      category
      priority
      isPinned
      publishedAt
      isRead
    }
  }
`;

const GET_UNREAD_COUNT = gql`
  query UnreadCount {
    unreadNewsCount
  }
`;

const MARK_AS_READ = gql`
  mutation MarkRead($newsId: UUID!) {
    markNewsAsRead(newsId: $newsId) {
      success
      unreadCount
    }
  }
`;
```

## Testing

Run unit tests:

```bash
cd /opt/hefaistos/backend
python manage.py test news
```

Tests cover:
- News post creation
- Auto-setting dates on publish
- Expiration logic
- Read status tracking
- Unique constraint enforcement

## Future Enhancements (Phase 2)

- [ ] Scheduled publishing (cron job)
- [ ] Email digest (weekly summary)
- [ ] Rich markdown editor (frontend)
- [ ] Reactions (emoji responses)
- [ ] Search and advanced filters
- [ ] News archive page
- [ ] RSS feed
- [ ] Analytics (view count, read rate)
- [ ] Targeted announcements (role-based)
- [ ] Attachments (PDFs, links)
- [ ] Multi-language support

## SMTP Configuration (For Email Digest)

Add to `docker-compose.yml`:

```yaml
backend:
  environment:
    - EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
    - EMAIL_HOST=smtp.gmail.com
    - EMAIL_PORT=587
    - EMAIL_USE_TLS=true
    - EMAIL_HOST_USER=your-email@gmail.com
    - EMAIL_HOST_PASSWORD=${SMTP_PASSWORD}
    - DEFAULT_FROM_EMAIL=noreply@hefaistos.io
```

Or in `settings.py`:

```python
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = get_secret('smtp_password', 'EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@hefaistos.io')
```

## Troubleshooting

### Migration Issues

```bash
# Reset migrations (dev only)
python manage.py migrate news zero
python manage.py showmigrations news
```

### No Unread Count

- Check that `UserNewsRead` records are created on mark-as-read
- Verify `is_published=True` on news posts
- Check expiration dates (`expires_at`)

### RabbitMQ Events Not Publishing

- Verify RabbitMQ is running: `docker compose ps rabbitmq`
- Check logs: `docker compose logs backend | grep news.published`
- Ensure `core.rabbitmq.publish_event` is imported

## License

Part of Hefaistos Detection Engineering Platform.
