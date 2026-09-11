"""
Custom GraphQL context for debugging and properly passing request context.
"""
import logging

logger = logging.getLogger(__name__)

def get_context(request):
    """
    Custom context function that ensures request and user are available to resolvers.
    This is needed for JWT authentication to work properly with graphene.
    """
    user = request.user if request else None
    
    # Debug logging for service accounts
    if user and hasattr(user, 'username'):
        if 'service' in user.username.lower() or user.username == 'connector_svc':
            logger.debug(f"[get_context] Service account detected: {user.username}")
    
    return {
        'request': request,
        'user': user,
    }
