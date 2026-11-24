import pytest

from student_cabinet import (
    AccessDenied,
    AuthError,
    CabinetService,
    Conflict,
    NotFound,
    Role,
    ValidationError,
    has_permission,
)
from student_cabinet.security import make_token, read_token


@pytest.fixture
def svc():
    s = CabinetService(":memory:", secret_key="test-secret")
    yield s
    s.close()


@pytest.fixture
def people(svc):
    ids = {
        "student": svc.register("ivan", "password1", "Иванов Иван"),
        "other": svc.register("petr", "password2", "Петров Пётр"),
        "teacher": svc.register("teach", "password3", "Сидорова А.", Role.TEACHER),
        "admin": svc.register("root", "password4", "Админ", Role.ADMIN),
    }
    actors = {
        name: svc.authenticate(svc.login(u, p))
        for name, (u, p) in {
            "student": ("ivan", "password1"),
            "other": ("petr", "password2"),
            "teacher": ("teach", "password3"),
            "admin": ("root", "password4"),
        }.items()
    }
    return ids, actors


# ---- регистрация и вход ----
def test_register_and_login_returns_valid_token(svc):
    uid = svc.register("ivan", "password1", "Иванов Иван")
    user = svc.authenticate(svc.login("ivan", "password1"))
    assert user["id"] == uid
    assert user["role"] == "student"


def test_duplicate_username_rejected(svc):
    svc.register("ivan", "password1", "Иванов Иван")
    with pytest.raises(Conflict):
        svc.register("ivan", "password9", "Другой")


@pytest.mark.parametrize(
    "username,password,name",
    [("a", "password1", "X"), ("ivan", "short", "X"), ("ivan", "password1", "  ")],
)
def test_register_validation(svc, username, password, name):
    with pytest.raises(ValidationError):
        svc.register(username, password, name)


def test_wrong_password_rejected(svc):
    svc.register("ivan", "password1", "Иванов Иван")
    with pytest.raises(AuthError):
        svc.login("ivan", "wrong-password")


def test_tampered_and_expired_tokens_rejected():
    token = make_token("s", 1, 60, now=1000)
    assert read_token("s", token, now=1010) == 1
    with pytest.raises(AuthError):
        read_token("s", token, now=2000)  # истёк
    with pytest.raises(AuthError):
        read_token("other-secret", token, now=1010)  # чужая подпись
    with pytest.raises(AuthError):
        read_token("s", "garbage", now=1010)


# ---- разграничение доступа ----
def test_student_reads_own_profile_but_not_foreign(svc, people):
    ids, actors = people
    assert svc.get_profile(actors["student"], ids["student"])["full_name"] == "Иванов Иван"
    with pytest.raises(AccessDenied):
        svc.get_profile(actors["student"], ids["other"])


def test_teacher_can_read_any_profile(svc, people):
    ids, actors = people
    assert svc.get_profile(actors["teacher"], ids["student"])["username"] == "ivan"


def test_student_cannot_put_grades_teacher_can(svc, people):
    ids, actors = people
    with pytest.raises(AccessDenied):
        svc.add_grade(actors["student"], ids["student"], "Математика", 5)
    svc.add_grade(actors["teacher"], ids["student"], "Математика", 5)
    grades = svc.get_grades(actors["student"], ids["student"])
    assert [(g["subject"], g["value"]) for g in grades] == [("Математика", 5)]


def test_student_cannot_see_foreign_grades(svc, people):
    ids, actors = people
    with pytest.raises(AccessDenied):
        svc.get_grades(actors["other"], ids["student"])


@pytest.mark.parametrize("value", [0, 6, "5", True, None])
def test_invalid_grade_values(svc, people, value):
    ids, actors = people
    with pytest.raises(ValidationError):
        svc.add_grade(actors["teacher"], ids["student"], "Физика", value)


def test_grade_for_unknown_student(svc, people):
    _, actors = people
    with pytest.raises(NotFound):
        svc.add_grade(actors["teacher"], 999, "Физика", 4)


# ---- профиль ----
def test_update_own_profile(svc, people):
    ids, actors = people
    p = svc.update_profile(actors["student"], ids["student"], email="i@mail.ru", group_name="4-1П9")
    assert p["email"] == "i@mail.ru" and p["group_name"] == "4-1П9"


def test_cannot_update_foreign_profile_or_forbidden_field(svc, people):
    ids, actors = people
    with pytest.raises(AccessDenied):
        svc.update_profile(actors["student"], ids["other"], phone="1")
    with pytest.raises(ValidationError):
        svc.update_profile(actors["student"], ids["student"], role="admin")
    with pytest.raises(ValidationError):
        svc.update_profile(actors["student"], ids["student"], email="не-почта")


# ---- администрирование ----
def test_only_admin_changes_roles(svc, people):
    ids, actors = people
    with pytest.raises(AccessDenied):
        svc.set_role(actors["teacher"], ids["student"], Role.ADMIN)
    svc.set_role(actors["admin"], ids["student"], "teacher")
    assert svc.authenticate(svc.login("ivan", "password1"))["role"] == "teacher"
    with pytest.raises(ValidationError):
        svc.set_role(actors["admin"], ids["student"], "king")


def test_list_users_admin_only(svc, people):
    _, actors = people
    assert len(svc.list_users(actors["admin"])) == 4
    with pytest.raises(AccessDenied):
        svc.list_users(actors["teacher"])


def test_list_students_for_teacher_only(svc, people):
    _, actors = people
    names = [s["username"] for s in svc.list_students(actors["teacher"])]
    assert names == ["ivan", "petr"]  # только студенты, по ФИО
    with pytest.raises(AccessDenied):
        svc.list_students(actors["student"])


def test_permission_matrix():
    assert has_permission("student", "grades:read_own")
    assert not has_permission("student", "grades:write")
    assert has_permission(Role.ADMIN, "users:manage")
