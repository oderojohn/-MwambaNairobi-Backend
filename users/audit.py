from typing import Any

from .models import UserAuditLog


def _get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_user_activity(
    *,
    action: str,
    user=None,
    request=None,
    status_code: int | None = None,
    metadata: dict[str, Any] | None = None,
    username: str = '',
):
    if metadata is None:
        metadata = {}

    profile = getattr(user, 'userprofile', None) if user else None

    payload = {
        'user': user if getattr(user, 'pk', None) else None,
        'user_profile': profile if getattr(profile, 'pk', None) else None,
        'username': username or getattr(user, 'username', '') or '',
        'role': getattr(profile, 'role', '') or '',
        'action': action,
        'status_code': status_code,
        'metadata': metadata,
    }

    if request is not None:
        payload.update({
            'method': getattr(request, 'method', '') or '',
            'path': getattr(request, 'path', '') or '',
            'ip_address': _get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:1000],
        })

    UserAuditLog.objects.create(**payload)
