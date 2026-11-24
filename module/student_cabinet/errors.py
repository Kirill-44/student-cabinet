"""Исключения модуля."""


class CabinetError(Exception):
    """Базовое исключение модуля."""


class ValidationError(CabinetError):
    """Некорректные входные данные (HTTP 400)."""


class AuthError(CabinetError):
    """Неверный логин/пароль или токен (HTTP 401)."""


class AccessDenied(CabinetError):
    """Недостаточно прав (HTTP 403)."""


class NotFound(CabinetError):
    """Объект не найден (HTTP 404)."""


class Conflict(CabinetError):
    """Конфликт, например логин уже занят (HTTP 409)."""
