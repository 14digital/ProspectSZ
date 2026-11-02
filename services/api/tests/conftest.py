import os
os.environ["DATABASE_URL"]="sqlite:///./test_api.sqlite3"
os.environ["APP_SECRET_KEY"]="test-secret-key-at-least-thirty-two-characters"
os.environ["ADMIN_EMAIL"]="admin@example.com"
os.environ["ADMIN_PASSWORD"]="correct-horse-battery-staple"

import pytest
from fastapi.testclient import TestClient
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.main import app
from app.models.entities import User

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(User(email="admin@example.com",password_hash=hash_password("correct-horse-battery-staple"),role="admin")); db.commit()
    yield

@pytest.fixture
def client(): return TestClient(app,raise_server_exceptions=True)
@pytest.fixture
def auth(client):
    response=client.post("/api/v1/auth/token",data={"username":"admin@example.com","password":"correct-horse-battery-staple"}); assert response.status_code==200
    return {"Authorization":f"Bearer {response.json()['access_token']}"}
