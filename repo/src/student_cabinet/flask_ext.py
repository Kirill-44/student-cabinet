"""Необязательная интеграция с Flask (импортируйте, только если используете Flask).

from student_cabinet.flask_ext import init_cabinet, login_required, roles_required
"""

from functools import wraps

from flask import g, jsonify, request

from .errors import (
    AccessDenied,
    AuthError,
    CabinetError,
    Conflict,
    NotFound,
    ValidationError,
)

_STATUS = {
    ValidationError: 400,
    AuthError: 401,
    AccessDenied: 403,
    NotFound: 404,
    Conflict: 409,
}


def init_cabinet(app, service):
    """Подключает сервис к приложению и регистрирует обработчик ошибок."""
    app.extensions["cabinet"] = service

    @app.errorhandler(CabinetError)
    def _handle(err):
        return jsonify(error=str(err)), _STATUS.get(type(err), 400)

    return service


def get_service():
    from flask import current_app

    return current_app.extensions["cabinet"]


def login_required(view):
    """Требует заголовок Authorization: Bearer <token>. Кладёт пользователя в g.user."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise AuthError("Нужен заголовок Authorization: Bearer <token>")
        g.user = get_service().authenticate(header[7:])
        return view(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    """Пускает только перечисленные роли (включает login_required)."""
    allowed = {getattr(r, "value", r) for r in roles}

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if g.user["role"] not in allowed:
                raise AccessDenied("Роль не допущена к этому действию")
            return view(*args, **kwargs)

        return wrapper

    return decorator
