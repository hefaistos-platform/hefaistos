from django.urls import path

from .api_views import profile_tokens, revoke_profile_token


urlpatterns = [
    path('tokens', profile_tokens, name='profile-tokens'),
    path('tokens/<int:token_id>/revoke', revoke_profile_token, name='profile-tokens-revoke'),
]
