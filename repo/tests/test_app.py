import pytest

from app import create_app
from seed import seed


@pytest.fixture
def app():
    app = create_app(db_path=":memory:", secret_key="test")
    seed(app)
    return app


class Browser:
    """Тонкая обёртка над test client: сама подставляет CSRF-токен в POST."""

    def __init__(self, client):
        self.c = client

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, **kw):
        self.c.get("/login")  # создаёт csrf в сессии
        with self.c.session_transaction() as s:
            token = s["csrf"]
        return self.c.post(url, data={**(data or {}), "csrf": token}, **kw)

    def login(self, username, password):
        return self.post("/login", {"username": username, "password": password})


@pytest.fixture
def web(app):
    return Browser(app.test_client())


def new_web(app):
    return Browser(app.test_client())


def test_register_login_and_see_cabinet(web):
    r = web.post(
        "/register", {"username": "petr", "password": "password1", "full_name": "Петров Пётр"}
    )
    assert r.status_code == 302
    web.login("petr", "password1")
    page = web.get("/cabinet").get_data(as_text=True)
    assert "Петров Пётр" in page and "Оценок пока нет" in page


def test_wrong_password_shows_error(web):
    r = web.login("ivan", "bad-password")
    assert "Неверный логин или пароль" in r.get_data(as_text=True)
    assert web.get("/cabinet").status_code == 302  # не вошли


def test_cabinet_requires_login(web):
    r = web.get("/cabinet")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_post_without_csrf_rejected(app):
    r = app.test_client().post("/login", data={"username": "ivan", "password": "student12345"})
    assert r.status_code == 400


def test_student_forbidden_on_teacher_and_admin_pages(web):
    web.login("ivan", "student12345")
    assert web.get("/students").status_code == 403
    assert web.get("/admin/users").status_code == 403
    assert web.get("/students/4").status_code == 403  # чужой профиль


def test_public_registration_cannot_choose_role(web):
    web.post(
        "/register",
        {"username": "hack", "password": "password1", "full_name": "X", "role": "admin"},
    )
    web.login("hack", "password1")
    assert web.get("/admin/users").status_code == 403


def test_teacher_grades_student_who_sees_it(app):
    teacher, student = new_web(app), new_web(app)
    teacher.login("teacher", "teacher12345")
    assert "Иванов Иван" in teacher.get("/students").get_data(as_text=True)
    r = teacher.post("/students/3/grades", {"subject": "Математика", "value": "5"})
    assert r.status_code == 302
    student.login("ivan", "student12345")
    page = student.get("/cabinet").get_data(as_text=True)
    assert "Математика" in page and "5.00" in page


def test_invalid_grade_is_rejected_with_message(web):
    web.login("teacher", "teacher12345")
    r = web.post("/students/3/grades", {"subject": "Физика", "value": "9"}, follow_redirects=True)
    assert "от 1 до 5" in r.get_data(as_text=True)


def test_admin_changes_role(app):
    admin, ivan = new_web(app), new_web(app)
    admin.login("admin", "admin12345")
    assert admin.post("/admin/users/3/role", {"role": "teacher"}).status_code == 302
    ivan.login("ivan", "student12345")
    assert ivan.get("/students").status_code == 200


def test_edit_profile(web):
    web.login("ivan", "student12345")
    web.post(
        "/profile/edit",
        {"full_name": "Иванов Иван", "group_name": "4-1П9", "email": "i@mail.ru", "phone": ""},
    )
    assert "4-1П9" in web.get("/cabinet").get_data(as_text=True)
