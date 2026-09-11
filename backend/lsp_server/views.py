"""
HTTP views for SyntaxTide LSP operational status.
"""

from django.http import JsonResponse

from lsp_server.manager import get_lsp_manager


def lsp_status(request):
    """Return per-language SyntaxTide LSP status for health monitoring."""
    manager = get_lsp_manager()
    languages = manager.get_status()

    running_count = sum(1 for info in languages.values() if info.get('running'))
    total_count = len(languages)

    return JsonResponse(
        {
            'status': 'ok' if running_count == total_count else 'degraded',
            'summary': {
                'running': running_count,
                'total': total_count,
            },
            'languages': languages,
        }
    )
