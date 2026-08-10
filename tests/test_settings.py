from app.auth import verify_password
from app.models import User


def register(client, username="alice", password="hunter2"):
    return client.post("/auth/register", data={"username": username, "password": password})


def test_user_can_change_password_via_settings(client):
    register(client, "alice", "old-password")

    response = client.post(
        "/settings",
        data={"current_password": "old-password", "new_username": "", "new_password": "new-password"},
    )

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        user = db.query(User).filter_by(username="alice").first()
        assert verify_password("new-password", user.password_hash)
        assert not verify_password("old-password", user.password_hash)
    finally:
        db.close()

    client.cookies.clear()
    login_response = client.post("/auth/login", data={"username": "alice", "password": "new-password"})
    assert login_response.status_code == 200


def test_settings_rejects_wrong_current_password(client):
    register(client, "bob", "correct-password")

    response = client.post(
        "/settings",
        data={"current_password": "wrong-password", "new_username": "", "new_password": "new-password"},
    )

    assert response.status_code == 400
    db = client.SessionLocal()
    try:
        user = db.query(User).filter_by(username="bob").first()
        assert verify_password("correct-password", user.password_hash)
    finally:
        db.close()


def test_user_can_change_username_via_settings(client):
    register(client, "carol", "pw")

    response = client.post(
        "/settings",
        data={"current_password": "pw", "new_username": "carolyn", "new_password": ""},
    )

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        assert db.query(User).filter_by(username="carolyn").first() is not None
        assert db.query(User).filter_by(username="carol").first() is None
    finally:
        db.close()


def test_settings_rejects_duplicate_username(client):
    register(client, "dave", "pw")
    register(client, "erin", "pw")
    client.post("/auth/login", data={"username": "dave", "password": "pw"})

    response = client.post(
        "/settings",
        data={"current_password": "pw", "new_username": "erin", "new_password": ""},
    )

    assert response.status_code == 400
    db = client.SessionLocal()
    try:
        assert db.query(User).filter_by(username="dave").first() is not None
    finally:
        db.close()


def test_settings_requires_login(client):
    response = client.get("/settings/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_admin_can_also_use_settings(client):
    register(client, "root", "pw")
    db = client.SessionLocal()
    try:
        user = db.query(User).filter_by(username="root").first()
        user.is_admin = True
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/settings",
        data={"current_password": "pw", "new_username": "", "new_password": "new-admin-pw"},
    )

    assert response.status_code == 200
    db = client.SessionLocal()
    try:
        user = db.query(User).filter_by(username="root").first()
        assert verify_password("new-admin-pw", user.password_hash)
    finally:
        db.close()
