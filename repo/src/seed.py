"""Создаёт демонстрационных пользователей: python src/seed.py"""

from app import create_app
from student_cabinet import CabinetError, Role

DEMO_USERS = [
    ("admin", "admin12345", "Администратор Системы", Role.ADMIN),
    ("teacher", "teacher12345", "Сидорова Анна Петровна", Role.TEACHER),
    ("ivan", "student12345", "Иванов Иван Сергеевич", Role.STUDENT),
    ("maria", "student12345", "Кузнецова Мария Олеговна", Role.STUDENT),
]


def seed(app):
    cabinet = app.extensions["cabinet"]
    created = []
    for username, password, full_name, role in DEMO_USERS:
        try:
            cabinet.register(username, password, full_name, role)
            created.append(username)
        except CabinetError:
            pass  # уже существует
    return created


if __name__ == "__main__":
    done = seed(create_app())
    print("Создано:", ", ".join(done) if done else "ничего (пользователи уже есть)")
