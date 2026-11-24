"""Роли и права доступа (RBAC)."""

from enum import Enum


class Role(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class Permission(str, Enum):
    PROFILE_READ_OWN = "profile:read_own"
    PROFILE_EDIT_OWN = "profile:edit_own"
    PROFILE_READ_ANY = "profile:read_any"
    GRADES_READ_OWN = "grades:read_own"
    GRADES_READ_ANY = "grades:read_any"
    GRADES_WRITE = "grades:write"
    USERS_MANAGE = "users:manage"


# Матрица "роль -> набор прав". Меняйте здесь, если нужны другие правила.
ROLE_PERMISSIONS = {
    Role.STUDENT: {
        Permission.PROFILE_READ_OWN,
        Permission.PROFILE_EDIT_OWN,
        Permission.GRADES_READ_OWN,
    },
    Role.TEACHER: {
        Permission.PROFILE_READ_OWN,
        Permission.PROFILE_EDIT_OWN,
        Permission.PROFILE_READ_ANY,
        Permission.GRADES_READ_OWN,
        Permission.GRADES_READ_ANY,
        Permission.GRADES_WRITE,
    },
    Role.ADMIN: set(Permission),
}


def has_permission(role, permission):
    """True, если у роли есть право."""
    return Permission(permission) in ROLE_PERMISSIONS[Role(role)]
