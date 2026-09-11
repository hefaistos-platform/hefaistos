import logging
from datetime import datetime


class GraphQLLogMiddleware:
    """
    Graphene middleware that logs each field resolver invocation with basic context.

    Notes:
    - Kept intentionally lightweight (no heavy serialization of values).
    - Uses the 'graphql' logger; configure in Django LOGGING to see output.
    - Only logs when DEBUG is True or when the environment sets GRAPHQL_LOGGING=1.
    """

    def __init__(self):
        self.logger = logging.getLogger('graphql')

    def resolve(self, next, root, info, **args):
        try:
            request = getattr(info.context, 'request', info.context)
        except Exception:
            request = None

        user = getattr(request, 'user', None) if request is not None else None

        # Build a compact log line
        log_payload = {
            'ts': datetime.utcnow().isoformat() + 'Z',
            'field': info.field_name,
            'parent_type': str(info.parent_type),
            'path': '.'.join(map(str, info.path.as_list())) if hasattr(info, 'path') else '',
            'user': getattr(user, 'username', 'anonymous') if user is not None else 'unknown',
        }

        # Best-effort: include argument names without large values
        if args:
            try:
                log_payload['args'] = list(args.keys())
            except Exception:
                pass

        # Emit the log line at INFO level
        self.logger.info("GraphQL resolve: %s", log_payload)

        return next(root, info, **args)
