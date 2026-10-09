"""Seed clearly labelled synthetic demo opportunities into the local database."""
from app.main import SessionLocal, seed_demo

if __name__ == "__main__":
    with SessionLocal() as db:
        seed_demo(db)
        print("Demo records seeded. These are synthetic examples, not real vacancies.")
