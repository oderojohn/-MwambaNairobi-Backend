from .audit import log_user_activity


class UserActivityAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, 'user', None)
        path = getattr(request, 'path', '')

        if (
            getattr(user, 'is_authenticated', False)
            and path.startswith('/api/')
            and not path.startswith('/api/auth/login/')
            and not path.startswith('/api/auth/refresh/')
        ):
            metadata = {}
            if request.GET:
                metadata['query_params'] = dict(request.GET.lists())

            log_user_activity(
                action='request',
                user=user,
                request=request,
                status_code=getattr(response, 'status_code', None),
                metadata=metadata,
            )

        return response
