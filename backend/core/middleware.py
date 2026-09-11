"""
(c) 2026 Jan Pohl a.k.a. M3C4N1SM0 & An Embarrassing Amount of AI Bots

Custom middleware for Hefaistos.
Lovingly crafted security measures that probably work better than they should.
"""
import ipaddress
import logging
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from core.mcs_logging import emit_security_event
from identity.decorators import is_bot_auditor_user

logger = logging.getLogger(__name__)


class BotReadOnlyHttpMiddleware:
    """
    Enforce read-only mode for bot auditor roles on non-GraphQL HTTP endpoints.
    GraphQL write protection is handled by core.graphql_security.GraphQLSecurityMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if (
            user
            and not getattr(user, 'is_anonymous', True)
            and is_bot_auditor_user(user)
            and request.method.upper() not in ('GET', 'HEAD', 'OPTIONS')
            and not request.path.startswith('/graphql')
        ):
            source_ip = request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', 'unknown')
            emit_security_event(
                level='warning',
                logger_name='AuthorizationService',
                message=(
                    f"Read-only bot account '{getattr(user, 'username', 'unknown')}' "
                    f"attempted HTTP write '{request.method} {request.path}'."
                ),
                event_action='resource_access_denied',
                event_outcome='failure',
                asvs_event_code='AUTHZ-DENY-01',
                event_reason='Read-only bot auditor accounts cannot perform write operations.',
                event_category=['authorization'],
                event_type=['denied', 'failure'],
                user_id=str(getattr(user, 'id', 'unknown')),
                user_name=getattr(user, 'username', None),
                source_ip=source_ip,
                request=request,
                http_status_code=403,
            )
            return HttpResponseForbidden('Read-only bot auditor accounts cannot perform this operation.')

        return self.get_response(request)


class AdminIPRestrictionMiddleware:
    """
    Restricts access to sensitive endpoints (/admin/, /graphql) to specific IP ranges.
    
    Configure ADMIN_ALLOWED_IP_RANGES in settings.py:
        ADMIN_ALLOWED_IP_RANGES = ['192.168.1.0/24', '10.0.0.0/8', '127.0.0.1']
    
    If not configured, defaults to private networks + localhost.
    Protects: /admin/, /graphql, /api/admin/ and any admin-related paths.
    """
    
    # Default allowed ranges (private networks + localhost)
    DEFAULT_ALLOWED_RANGES = [
        '127.0.0.1/32',      # localhost IPv4
        '::1/128',           # localhost IPv6
        '10.0.0.0/8',        # Private Class A
        '172.16.0.0/12',     # Private Class B
        '91.99.117.25/32',   # VPS Address
        '185.91.166.204/32'  # Home VPN
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Get allowed ranges from settings or use defaults
        self.allowed_ranges = getattr(
            settings, 
            'ADMIN_ALLOWED_IP_RANGES', 
            self.DEFAULT_ALLOWED_RANGES
        )
        # Parse IP networks
        self.networks = []
        for ip_range in self.allowed_ranges:
            try:
                self.networks.append(ipaddress.ip_network(ip_range, strict=False))
            except ValueError:
                # If it's a single IP without CIDR notation
                try:
                    self.networks.append(ipaddress.ip_network(f"{ip_range}/32", strict=False))
                except ValueError:
                    pass  # Invalid IP, skip it
        
        logger.info(f"AdminIPRestriction: Configured networks: {[str(n) for n in self.networks]}")
    
    def __call__(self, request):
        # Check sensitive paths: /admin/, /graphql, and other admin-related endpoints
        restricted_paths = [
            '/admin',           # Django admin
            '/graphql',         # GraphQL API
            '/api/admin/',      # Admin API endpoints
            '/api/graphql',     # Alternative GraphQL path
        ]
        
        is_restricted = any(request.path.startswith(path) for path in restricted_paths)
        
        if is_restricted:
            client_ip = self.get_client_ip(request)
            
            # Debug logging
            logger.info(f"Restricted path access attempt - IP: {client_ip}, Path: {request.path}")
            logger.debug(f"X-Forwarded-For: {request.META.get('HTTP_X_FORWARDED_FOR')}")
            logger.debug(f"X-Real-IP: {request.META.get('HTTP_X_REAL_IP')}")
            logger.debug(f"REMOTE_ADDR: {request.META.get('REMOTE_ADDR')}")
            
            if not self.is_ip_allowed(client_ip):
                logger.warning(f"Restricted access DENIED for IP: {client_ip}, Path: {request.path}")
                emit_security_event(
                    level='warning',
                    logger_name='AuthorizationService',
                    message=(
                        f"Restricted endpoint access denied for IP '{client_ip}' "
                        f"to path '{request.path}'."
                    ),
                    event_action='resource_access_denied',
                    event_outcome='failure',
                    asvs_event_code='AUTHZ-DENY-01',
                    event_reason='Source IP is not in allowed admin ranges.',
                    event_category=['authorization', 'network'],
                    event_type=['denied', 'failure'],
                    user_id='anonymous',
                    source_ip=client_ip,
                    request=request,
                    http_status_code=403,
                    asvs_details={
                        'authorization': {
                            'resource_type': 'http_endpoint',
                            'resource_id': request.path,
                            'required_permission': 'network:admin_allowed_range',
                        }
                    },
                )
                return HttpResponseForbidden(
                    '<h1>403 Forbidden</h1>'
                    f'<p>Access to this resource is restricted to authorized networks only.</p>'
                    f'<p>Your IP: {client_ip}</p>'
                )
            
            logger.info(f"Restricted access ALLOWED for IP: {client_ip}, Path: {request.path}")
        
        return self.get_response(request)
    
    def get_client_ip(self, request):
        """
        Get the real client IP, accounting for proxies.
        Checks headers in order of priority:
        1. X-Real-IP (commonly set by nginx)
        2. X-Forwarded-For (first IP in chain)
        3. REMOTE_ADDR (fallback)
        """
        # Try X-Real-IP first (often set by nginx)
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()
        
        # Try X-Forwarded-For
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Take the first IP in the chain (original client)
            return x_forwarded_for.split(',')[0].strip()
        
        # Fallback to REMOTE_ADDR
        return request.META.get('REMOTE_ADDR', '')
    
    def is_ip_allowed(self, ip_str):
        """Check if the IP is in any of the allowed ranges."""
        if not ip_str:
            return False
        
        try:
            client_ip = ipaddress.ip_address(ip_str)
            for network in self.networks:
                if client_ip in network:
                    return True
        except ValueError:
            # Invalid IP address
            logger.error(f"Invalid IP address: {ip_str}")
            return False
        
        return False


class ContentLengthValidationMiddleware(MiddlewareMixin):
    """
    Mitigates Client-Side Desync (CSD) attacks by:
    1. Validating Content-Length header matches actual body size
    2. Logging mismatches for security monitoring
    
    Note: Connection management is handled by nginx, not Django.
    Fixes: CWE-444 (HTTP Request Smuggling)
    """
    
    MAX_BODY_SIZE = 20 * 1024 * 1024  # 20MB limit for base64-encoded 10MB uploads
    
    def process_request(self, request):
        """
        Validate Content-Length for POST/PUT/PATCH requests.
        """
        # Only validate POST/PUT/PATCH requests (stateful operations)
        if request.method not in ('POST', 'PUT', 'PATCH'):
            return None
        
        content_length = request.META.get('CONTENT_LENGTH', '')

        # Allow requests without Content-Length (chunked encoding, empty body)
        # This is valid for some API calls
        if not content_length:
            return None
        
        # Validate Content-Length is numeric and reasonable
        try:
            content_len = int(content_length)
            if content_len < 0:
                raise ValueError("Negative Content-Length")
            if content_len > self.MAX_BODY_SIZE:
                logger.warning(
                    f"Content-Length exceeds limit ({content_len} > {self.MAX_BODY_SIZE}): "
                    f"{request.method} {request.path}"
                )
                return HttpResponseBadRequest('Request body too large')
        except ValueError:
            logger.warning(
                f"Invalid Content-Length '{content_length}': {request.method} {request.path}"
            )
            return HttpResponseBadRequest('Invalid Content-Length header')
        
        # Validate body length matches Content-Length (only for non-zero bodies)
        if content_len > 0:
            try:
                _ = request.body
                actual_len = len(request.body)
                
                if actual_len != content_len:
                    logger.error(
                        f"Content-Length mismatch: declared={content_len}, actual={actual_len} "
                        f"at {request.method} {request.path}. Potential desync attempt."
                    )
                    # Flag for monitoring but don't block - nginx handles connection
                    request._content_length_mismatch = True
            except Exception as e:
                logger.error(
                    f"Error reading request body: {str(e)} for {request.method} {request.path}"
                )
        
        return None


class RequestBodyConsumptionMiddleware(MiddlewareMixin):
    """
    Logs security-relevant request patterns for monitoring.
    Note: Connection management must be handled by nginx, not Django WSGI.
    """
    
    def process_response(self, request, response):
        """
        Log security-relevant patterns. Connection headers are hop-by-hop
        and cannot be set by WSGI applications.
        """
        # Log if there was a content-length mismatch
        if getattr(request, '_content_length_mismatch', False):
            logger.warning(
                f"Response sent after Content-Length mismatch: {request.method} {request.path}"
            )
        
        return response


class CORSPrivateNetworkMiddleware:
    """
    Adds Access-Control-Allow-Private-Network header to CORS responses.
    Required for Chrome's Private Network Access (PNA) policy when public sites
    (like mitre-attack.github.io) access local/private IP addresses.

    See: https://developer.chrome.com/blog/private-network-access-preflight/
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Add Private Network Access header for /api/ endpoints
        if request.path.startswith('/api/'):
            origin = request.META.get('HTTP_ORIGIN', '')
            # Only add for allowed CORS origins (specifically mitre-attack.github.io)
            if 'mitre-attack.github.io' in origin:
                response['Access-Control-Allow-Private-Network'] = 'true'

        return response


class CSDSecurityHeadersMiddleware(MiddlewareMixin):
    """
    Adds security headers to help prevent request smuggling and related attacks.
    Note: Connection-level headers (Connection, Keep-Alive) are hop-by-hop
    and must be configured in nginx, not Django.
    """
    def process_response(self, request, response):
        """
        Add headers to prevent CSD and related vulnerabilities.
        """
        # Prevent framing
        if 'X-Frame-Options' not in response:
            response['X-Frame-Options'] = 'DENY'
        
        # Prevent MIME type sniffing
        if 'X-Content-Type-Options' not in response:
            response['X-Content-Type-Options'] = 'nosniff'
        
        # Strict Transport Security
        if 'Strict-Transport-Security' not in response:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response
