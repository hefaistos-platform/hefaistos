# News app tests
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from .models import NewsPost, UserNewsRead

User = get_user_model()


class NewsPostModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='testpass123'
        )
    
    def test_create_news_post(self):
        """Test creating a news post"""
        post = NewsPost.objects.create(
            title="Test News",
            content="This is a test announcement",
            author=self.user,
            priority='HIGH',
            category='FEATURE'
        )
        self.assertIsNotNone(post.id)
        self.assertFalse(post.is_published)
        self.assertIsNone(post.published_at)
    
    def test_publish_sets_dates(self):
        """Test that publishing sets published_at and expires_at"""
        post = NewsPost.objects.create(
            content="Test content",
            author=self.user
        )
        post.is_published = True
        post.save()
        
        self.assertIsNotNone(post.published_at)
        self.assertIsNotNone(post.expires_at)
        # Should expire in 180 days
        expected_expiry = post.published_at + timedelta(days=180)
        self.assertAlmostEqual(
            post.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=1  # Within 1 second
        )
    
    def test_is_expired(self):
        """Test expiration check"""
        past_date = timezone.now() - timedelta(days=1)
        post = NewsPost.objects.create(
            content="Expired post",
            author=self.user,
            is_published=True,
            expires_at=past_date
        )
        self.assertTrue(post.is_expired())
    
    def test_is_active(self):
        """Test active status"""
        post = NewsPost.objects.create(
            content="Active post",
            author=self.user,
            is_published=True
        )
        post.save()  # Triggers auto-set of dates
        self.assertTrue(post.is_active)


class UserNewsReadModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='user@test.com',
            password='testpass123'
        )
        self.admin = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='testpass123'
        )
        self.post = NewsPost.objects.create(
            content="Test news",
            author=self.admin,
            is_published=True
        )
    
    def test_mark_as_read(self):
        """Test marking a post as read"""
        read_record = UserNewsRead.objects.create(
            user=self.user,
            news_post=self.post
        )
        self.assertIsNotNone(read_record.read_at)
    
    def test_unique_constraint(self):
        """Test that user can't mark same post as read twice"""
        UserNewsRead.objects.create(user=self.user, news_post=self.post)
        
        # Try to create duplicate - should raise IntegrityError
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            UserNewsRead.objects.create(user=self.user, news_post=self.post)
