import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.session import Base, engine, SessionLocal
from app.db.base import *
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.emails import router as emails_router
from app.models.user import User

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def run_schema_upgrades():
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_subject VARCHAR",
        "ALTER TABLE gmail_accounts ADD COLUMN IF NOT EXISTS google_subject VARCHAR",
        "ALTER TABLE gmail_accounts ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT",
        "ALTER TABLE gmail_accounts ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT",
        "ALTER TABLE gmail_accounts ADD COLUMN IF NOT EXISTS scopes TEXT",
        "ALTER TABLE gmail_accounts ADD COLUMN IF NOT EXISTS last_history_id VARCHAR",
        "ALTER TABLE gmail_accounts ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE emails ADD COLUMN IF NOT EXISTS gmail_account_id INTEGER REFERENCES gmail_accounts(id)",
        "ALTER TABLE emails ADD COLUMN IF NOT EXISTS gmail_label_ids TEXT",
        "ALTER TABLE email_embeddings ALTER COLUMN embedding TYPE vector USING embedding::vector",
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def init_db(retries: int = 10, delay: int = 3):
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                connection.commit()
                connection.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            run_schema_upgrades()
            print("Database connected, pgvector enabled, and tables created.")
            return
        except OperationalError as e:
            print(f"Database not ready yet (attempt {attempt}/{retries}): {e}")
            time.sleep(delay)

    raise Exception("Could not connect to the database after multiple retries.")


@app.on_event("startup")
def startup():
    init_db()

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.id == 1).first()
        if not existing:
            user = User(id=1, email="test@example.com", name="Test User")
            db.add(user)
            db.commit()
    finally:
        db.close()


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(emails_router)
