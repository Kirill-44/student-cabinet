"""student_cabinet - модуль личного кабинета студента с ролями и разграничением доступа."""

from .errors import (
    AccessDenied,
    AuthError,
    CabinetError,
    Conflict,
    NotFound,
    ValidationError,
)
from .roles import ROLE_PERMISSIONS, Permission, Role, has_permission
from .service import CabinetService

__version__ = "0.1.0"

__all__ = [
    "CabinetService",
    "Role",
    "Permission",
    "ROLE_PERMISSIONS",
    "has_permission",
    "CabinetError",
    "ValidationError",
    "AuthError",
    "AccessDenied",
    "NotFound",
    "Conflict",
]
