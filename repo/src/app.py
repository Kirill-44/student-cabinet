"""Учебный портал: Flask + Jinja2, личный кабинет построен на модуле student_cabinet."""

import os
import secrets
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from student_cabinet import (
    AccessDenied,
    AuthError,
    CabinetError,
    CabinetService,
    NotFound,
    Role,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app(db_path=None, secret_key=None):
    app = Flask(__name__)
    secret = secret_key or os.environ.get("PORTAL_SECRET", "dev-secret-change-me")
    app.secret_key = secret
    # Один и тот же сервис модуля используется во всех обработчиках.
    cabinet = CabinetService(
        db_path=db_path or os.environ.get("PORTAL_DB", os.path.join(BASE_DIR, "portal.db")),
        secret_key=secret,
    )
    app.extensions["cabinet"] = cabinet

    # ---------- защита форм (CSRF) и контекст шаблонов ----------
    @app.before_request
    def csrf_protect():
        if request.method == "POST":
            token = session.get("csrf")
            if not token or request.form.get("csrf") != token:
                abort(400, "Неверный CSRF-токен")

    @app.context_processor
    def inject_globals():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return {"csrf_token": session["csrf"], "user": g.get("user"), "Role": Role}

    # ---------- декоратор входа ----------
    def login_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            token = session.get("token")
            if not token:
                return redirect(url_for("login"))
            g.user = cabinet.authenticate(token)  # AuthError -> обработчик ниже
            return view(*args, **kwargs)

        return wrapper

    # ---------- ошибки модуля -> страницы ----------
    @app.errorhandler(AuthError)
    def on_auth_error(err):
        session.pop("token", None)
        flash(str(err), "error")
        return redirect(url_for("login"))

    @app.errorhandler(AccessDenied)
    def on_denied(err):
        return render_template("error.html", code=403, message=str(err)), 403

    @app.errorhandler(NotFound)
    def on_not_found(err):
        return render_template("error.html", code=404, message=str(err)), 404

    @app.errorhandler(400)
    def on_bad_request(err):
        return render_template("error.html", code=400, message=err.description), 400

    # ---------- публичные страницы ----------
    @app.get("/")
    def index():
        return redirect(url_for("cabinet_page" if session.get("token") else "login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            try:
                # Публично регистрируются только студенты.
                cabinet.register(
                    request.form.get("username", "").strip(),
                    request.form.get("password", ""),
                    request.form.get("full_name", ""),
                    Role.STUDENT,
                )
            except CabinetError as err:
                flash(str(err), "error")
            else:
                flash("Регистрация успешна. Теперь войдите.", "ok")
                return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            try:
                session["token"] = cabinet.login(
                    request.form.get("username", "").strip(), request.form.get("password", "")
                )
            except CabinetError as err:
                flash(str(err), "error")
            else:
                return redirect(url_for("cabinet_page"))
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.pop("token", None)
        return redirect(url_for("login"))

    # ---------- личный кабинет ----------
    @app.get("/cabinet")
    @login_required
    def cabinet_page():
        profile = cabinet.get_profile(g.user, g.user["id"])
        grades = cabinet.get_grades(g.user, g.user["id"])
        return render_template("cabinet.html", profile=profile, grades=grades)

    @app.route("/profile/edit", methods=["GET", "POST"])
    @login_required
    def edit_profile():
        if request.method == "POST":
            fields = {
                k: request.form.get(k, "").strip()
                for k in ("full_name", "group_name", "email", "phone")
            }
            try:
                cabinet.update_profile(g.user, g.user["id"], **fields)
            except CabinetError as err:
                flash(str(err), "error")
            else:
                flash("Профиль сохранён", "ok")
                return redirect(url_for("cabinet_page"))
        return render_template(
            "edit_profile.html", profile=cabinet.get_profile(g.user, g.user["id"])
        )

    # ---------- преподаватель ----------
    @app.get("/students")
    @login_required
    def students():
        return render_template("students.html", students=cabinet.list_students(g.user))

    @app.get("/students/<int:student_id>")
    @login_required
    def student_detail(student_id):
        return render_template(
            "student_detail.html",
            profile=cabinet.get_profile(g.user, student_id),
            grades=cabinet.get_grades(g.user, student_id),
        )

    @app.post("/students/<int:student_id>/grades")
    @login_required
    def add_grade(student_id):
        try:
            value = int(request.form.get("value", ""))
            cabinet.add_grade(g.user, student_id, request.form.get("subject", ""), value)
        except ValueError:
            flash("Оценка должна быть числом от 1 до 5", "error")
        except (AccessDenied, NotFound):
            raise
        except CabinetError as err:
            flash(str(err), "error")
        else:
            flash("Оценка выставлена", "ok")
        return redirect(url_for("student_detail", student_id=student_id))

    # ---------- администратор ----------
    @app.get("/admin/users")
    @login_required
    def admin_users():
        return render_template("admin_users.html", users=cabinet.list_users(g.user))

    @app.post("/admin/users/<int:user_id>/role")
    @login_required
    def set_role(user_id):
        try:
            cabinet.set_role(g.user, user_id, request.form.get("role"))
        except (AccessDenied, NotFound):
            raise
        except CabinetError as err:
            flash(str(err), "error")
        else:
            flash("Роль изменена", "ok")
        return redirect(url_for("admin_users"))

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
