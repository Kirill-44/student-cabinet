"""Основной сервис личного кабинета студента."""

import re
import sqlite3
import threading

from .errors import AccessDenied, AuthError, Conflict, NotFound, ValidationError
from .roles import Permission, Role, has_permission
from .security import hash_password, make_token, read_token, verify_password

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student'
);
CREATE TABLE IF NOT EXISTS profiles (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    full_name  TEXT NOT NULL,
    group_name TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS grades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    subject    TEXT NOT NULL,
    value      INTEGER NOT NULL CHECK (value BETWEEN 1 AND 5)
);
"""

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_EDITABLE_FIELDS = ("full_name", "group_name", "email", "phone")


class CabinetService:
    """Регистрация, вход, профиль, оценки и управление ролями.

    :param db_path: путь к SQLite-файлу или ":memory:".
    :param secret_key: секрет для подписи токенов.
    :param token_ttl: время жизни токена в секундах.
    """

    def __init__(self, db_path=":memory:", secret_key=None, token_ttl=3600):
        if not secret_key:
            raise ValueError("secret_key обязателен")
        self._secret = secret_key
        self._ttl = token_ttl
        self._lock = threading.RLock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(_SCHEMA)

    # ---------- аутентификация ----------
    def register(self, username, password, full_name, role=Role.STUDENT):
        """Создаёт пользователя и пустой профиль. Возвращает id."""
        if not _USERNAME_RE.match(username or ""):
            raise ValidationError("Логин: 3-32 символа (латиница, цифры, _ . -)")
        if len(password or "") < 8:
            raise ValidationError("Пароль должен быть не короче 8 символов")
        if not (full_name or "").strip():
            raise ValidationError("Укажите ФИО")
        role = self._parse_role(role)
        with self._lock:
            try:
                cur = self._db.execute(
                    "INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
                    (username, hash_password(password), role.value),
                )
            except sqlite3.IntegrityError:
                raise Conflict("Логин уже занят")
            self._db.execute(
                "INSERT INTO profiles(user_id, full_name) VALUES (?,?)",
                (cur.lastrowid, full_name.strip()),
            )
            self._db.commit()
            return cur.lastrowid

    def login(self, username, password):
        """Возвращает токен доступа."""
        row = self._db.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None or not verify_password(password or "", row["password_hash"]):
            raise AuthError("Неверный логин или пароль")
        return make_token(self._secret, row["id"], self._ttl)

    def authenticate(self, token):
        """По токену возвращает словарь пользователя (id, username, role)."""
        user_id = read_token(self._secret, token or "")
        user = self._get_user(user_id)
        if user is None:
            raise AuthError("Пользователь не найден")
        return user

    # ---------- профиль ----------
    def get_profile(self, actor, user_id):
        if actor["id"] == user_id:
            self._require(actor, Permission.PROFILE_READ_OWN)
        else:
            self._require(actor, Permission.PROFILE_READ_ANY)
        row = self._db.execute(
            "SELECT u.id, u.username, u.role, p.full_name, p.group_name, p.email, p.phone "
            "FROM users u JOIN profiles p ON p.user_id = u.id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise NotFound("Профиль не найден")
        return dict(row)

    def update_profile(self, actor, user_id, **fields):
        # Редактировать можно только свой профиль (админ - любой).
        if actor["id"] != user_id:
            self._require(actor, Permission.USERS_MANAGE)
        else:
            self._require(actor, Permission.PROFILE_EDIT_OWN)
        unknown = set(fields) - set(_EDITABLE_FIELDS)
        if unknown:
            raise ValidationError(f"Нельзя менять поля: {', '.join(sorted(unknown))}")
        if "email" in fields and fields["email"] and not _EMAIL_RE.match(fields["email"]):
            raise ValidationError("Некорректный email")
        if "full_name" in fields and not fields["full_name"].strip():
            raise ValidationError("ФИО не может быть пустым")
        if not fields:
            return self.get_profile(actor, user_id)
        with self._lock:
            if self._get_user(user_id) is None:
                raise NotFound("Профиль не найден")
            sets = ", ".join(f"{k} = ?" for k in fields)
            self._db.execute(
                f"UPDATE profiles SET {sets} WHERE user_id = ?",
                (*fields.values(), user_id),
            )
            self._db.commit()
        return self.get_profile(actor, user_id)

    # ---------- оценки ----------
    def add_grade(self, actor, student_id, subject, value):
        self._require(actor, Permission.GRADES_WRITE)
        if not (subject or "").strip():
            raise ValidationError("Укажите предмет")
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
            raise ValidationError("Оценка - целое число от 1 до 5")
        student = self._get_user(student_id)
        if student is None or student["role"] != Role.STUDENT.value:
            raise NotFound("Студент не найден")
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO grades(student_id, teacher_id, subject, value) VALUES (?,?,?,?)",
                (student_id, actor["id"], subject.strip(), value),
            )
            self._db.commit()
            return cur.lastrowid

    def get_grades(self, actor, student_id):
        if actor["id"] == student_id:
            self._require(actor, Permission.GRADES_READ_OWN)
        else:
            self._require(actor, Permission.GRADES_READ_ANY)
        rows = self._db.execute(
            "SELECT id, subject, value, teacher_id FROM grades " "WHERE student_id = ? ORDER BY id",
            (student_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_students(self, actor):
        """Список студентов (для преподавателя и администратора)."""
        self._require(actor, Permission.PROFILE_READ_ANY)
        rows = self._db.execute(
            "SELECT u.id, u.username, p.full_name, p.group_name FROM users u "
            "JOIN profiles p ON p.user_id = u.id WHERE u.role = ? ORDER BY p.full_name",
            (Role.STUDENT.value,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- администрирование ----------
    def set_role(self, actor, user_id, role):
        self._require(actor, Permission.USERS_MANAGE)
        role = self._parse_role(role)
        with self._lock:
            if self._get_user(user_id) is None:
                raise NotFound("Пользователь не найден")
            self._db.execute("UPDATE users SET role = ? WHERE id = ?", (role.value, user_id))
            self._db.commit()

    def list_users(self, actor):
        self._require(actor, Permission.USERS_MANAGE)
        rows = self._db.execute(
            "SELECT u.id, u.username, u.role, p.full_name FROM users u "
            "JOIN profiles p ON p.user_id = u.id ORDER BY u.id"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------- служебное ----------
    def close(self):
        self._db.close()

    def _get_user(self, user_id):
        row = self._db.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _parse_role(role):
        try:
            return Role(role)
        except ValueError:
            raise ValidationError(f"Неизвестная роль: {role}")

    @staticmethod
    def _require(actor, permission):
        if not has_permission(actor["role"], permission):
            raise AccessDenied(f"Нет права {Permission(permission).value}")
