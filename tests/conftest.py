import os
import warnings

os.environ.setdefault("ONEPOINT_SECRET_KEY", "test-secret-key-that-is-at-least-32-chars-long")
warnings.filterwarnings("ignore", message=".*does \\*not\\* support Decimal.*")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db, make_engine
from app.main import app

PASSWORD = "Str0ng!Passw0rd"


@pytest.fixture()
def client():
    engine = make_engine("sqlite://")  # fresh in-memory DB per test
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # No `with`: skip lifespan, which would create tables on the real engine.
    yield TestClient(app)
    app.dependency_overrides.clear()


def register_and_login(client, email="amara@example.com"):
    r = client.post("/auth/register", json={"email": email, "full_name": "Amara Kamara", "password": PASSWORD})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    tokens = r.json()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}
