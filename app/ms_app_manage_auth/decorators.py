# tu_app/decorators.py

from django.shortcuts import redirect
from functools import wraps

def permission_required(permission):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not request.user.has_permission(permission):
                return redirect('no_permission')  # Crea una vista para manejar accesos denegados
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
