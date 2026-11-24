# student_cabinet — модуль личного кабинета студента

Модуль даёт готовую логику личного кабинета:

- регистрация и вход (пароли хранятся в виде PBKDF2-хэша, доступ — по подписанному токену с TTL);
- три роли: `student`, `teacher`, `admin` и матрица прав (RBAC);
- профиль студента (ФИО, группа, email, телефон);
- оценки: преподаватель выставляет, студент смотрит свои;
- администратор меняет роли и видит список пользователей;
- хранение в SQLite (стандартная библиотека), **внешних зависимостей нет**.
  Flask нужен только для необязательных декораторов `flask_ext`.


## Структура

```
module/
├── README.md              <- вы здесь
├── student_cabinet/
│   ├── __init__.py        # публичный API
│   ├── service.py         # CabinetService - вся бизнес-логика
│   ├── roles.py           # Role, Permission, матрица ROLE_PERMISSIONS
│   ├── security.py        # хэш паролей, токены
│   ├── errors.py          # исключения
│   └── flask_ext.py       # (опционально) декораторы для Flask
└── tests/test_service.py  # 23 unit-теста
```

## Как внедрить в свой проект

Модуль подключается простым копированием, ничего устанавливать не нужно:

1. Скопируйте папку `student_cabinet/` (именно её, не всю `module/`) в корень вашего проекта —
   рядом с вашим `app.py` (или в `src/`, если запускаете оттуда).
2. Импортируйте:

```python
from student_cabinet import CabinetService, Role
```

Проверка, что всё встало (из папки проекта):

```bash
python -c "import student_cabinet; print(student_cabinet.__version__)"
```

Нужна только стандартная библиотека Python 3.9+. Flask требуется лишь если вы
подключаете `student_cabinet.flask_ext`.

## Как пользоваться

### 1. Создать сервис (один раз при старте приложения)

```python
from student_cabinet import CabinetService, Role

cabinet = CabinetService(
    db_path="cabinet.db",         # файл БД; ":memory:" - для тестов
    secret_key="длинный-секрет",  # храните в переменной окружения!
    token_ttl=3600,               # жизнь токена, сек (по умолчанию час)
)
```

### 2. Регистрация и вход

```python
student_id = cabinet.register("ivan", "password1", "Иванов Иван")        # роль student
cabinet.register("teacher1", "password2", "Сидорова А.", Role.TEACHER)

token = cabinet.login("ivan", "password1")   # строка-токен, отдайте клиенту
actor = cabinet.authenticate(token)          # {"id": 1, "username": "ivan", "role": "student"}
```

### 3. Работа с кабинетом — всегда передаём `actor` (кто выполняет действие)

```python
cabinet.get_profile(actor, student_id)
cabinet.update_profile(actor, student_id, email="ivan@mail.ru", group_name="4-1П9")

teacher = cabinet.authenticate(cabinet.login("teacher1", "password2"))
cabinet.add_grade(teacher, student_id, "Математика", 5)
cabinet.get_grades(actor, student_id)        # [{"id":1,"subject":"Математика","value":5,...}]
cabinet.list_students(teacher)               # список студентов (преподаватель/админ)

admin = cabinet.authenticate(cabinet.login("root", "..."))
cabinet.set_role(admin, student_id, "teacher")
cabinet.list_users(admin)
```

Сервис сам проверяет права. Если их нет — бросает исключение, ничего не меняя.

### 4. Исключения

| Исключение        | Когда                               | HTTP |
|-------------------|-------------------------------------|------|
| `ValidationError` | плохие входные данные               | 400  |
| `AuthError`       | неверный пароль / плохой токен      | 401  |
| `AccessDenied`    | у роли нет права на действие        | 403  |
| `NotFound`        | пользователь/профиль не найден      | 404  |
| `Conflict`        | логин уже занят                     | 409  |

Все наследуются от `CabinetError`.

### 5. Права ролей

| Право                | student | teacher | admin |
|----------------------|:-------:|:-------:|:-----:|
| `profile:read_own`   |    +    |    +    |   +   |
| `profile:edit_own`   |    +    |    +    |   +   |
| `profile:read_any`   |         |    +    |   +   |
| `grades:read_own`    |    +    |    +    |   +   |
| `grades:read_any`    |         |    +    |   +   |
| `grades:write`       |         |    +    |   +   |
| `users:manage`       |         |         |   +   |

Правила лежат в `roles.py` (`ROLE_PERMISSIONS`) — добавьте роль или право одной правкой.
Проверка вручную: `has_permission("student", "grades:write")  # False`.

### 6. Интеграция с Flask (опционально)

```python
from flask import Flask, g, jsonify
from student_cabinet.flask_ext import init_cabinet, login_required, roles_required

app = Flask(__name__)
init_cabinet(app, cabinet)   # ошибки модуля автоматически превращаются в JSON + HTTP-коды

@app.get("/me")
@login_required                      # заголовок Authorization: Bearer <token>
def me():
    return jsonify(cabinet.get_profile(g.user, g.user["id"]))

@app.get("/admin/users")
@roles_required("admin")             # только админ; иначе 403
def users():
    return jsonify(cabinet.list_users(g.user))
```

Рабочий пример — сайт в папке `repo/` (файл `src/app.py`).

## Запуск тестов модуля

Из папки `module` (нужен `pytest`):

```bash
cd module
python -m pytest
```

## Ограничения версии 0.1.0

- нет сброса пароля и подтверждения email;
- нет ограничения числа попыток входа;
- токен нельзя отозвать до истечения TTL (простой stateless-вариант);
- SQLite подходит для учебных и небольших проектов.
