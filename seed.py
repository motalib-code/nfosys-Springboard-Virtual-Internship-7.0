import sys
import os
from passlib.context import CryptContext

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), ".")))

from app.db.session import SessionLocal, Base, engine
from app.models import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def seed_data():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if users already exist
        existing_users = db.query(User).count()
        if existing_users > 0:
            print(f"Database already contains {existing_users} users. Skipping seed.")
            return

        password = "Password123!"
        hashed_password = get_password_hash(password)

        users = [
            User(
                name="Admin User",
                email="admin@example.com",
                password_hash=hashed_password,
                role=UserRole.ADMIN,
                is_active=True
            ),
            User(
                name="Examiner User",
                email="examiner@example.com",
                password_hash=hashed_password,
                role=UserRole.EXAMINER,
                is_active=True
            ),
            User(
                name="Student One",
                email="student1@example.com",
                password_hash=hashed_password,
                role=UserRole.STUDENT,
                is_active=True
            ),
            User(
                name="Student Two",
                email="student2@example.com",
                password_hash=hashed_password,
                role=UserRole.STUDENT,
                is_active=True
            ),
            User(
                name="Student Three",
                email="student3@example.com",
                password_hash=hashed_password,
                role=UserRole.STUDENT,
                is_active=True
            ),
        ]

        db.add_all(users)
        db.commit()
        print("Successfully seeded 1 admin, 1 examiner, and 3 students into the database.")
        print("Default password for all users is: Password123!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
