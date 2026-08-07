from app.models import User


def register(client, username="alice", password="hunter2"):
    return client.post("/auth/register", data={"username": username, "password": password})


def test_register_creates_user_and_sets_session_cookie(client):
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert body["is_admin"] is False
    assert "session_token" in response.cookies


def test_register_duplicate_username_rejected(client):
    register(client)
    response = register(client)

    assert response.status_code == 400


def test_login_with_correct_credentials_succeeds(client):
    register(client, "bob", "correct-password")
    client.cookies.clear()

    response = client.post("/auth/login", data={"username": "bob", "password": "correct-password"})

    assert response.status_code == 200
    assert "session_token" in response.cookies


def test_login_with_wrong_password_rejected(client):
    register(client, "carol", "correct-password")
    client.cookies.clear()

    response = client.post("/auth/login", data={"username": "carol", "password": "wrong-password"})

    assert response.status_code == 401


def test_login_with_unknown_username_rejected(client):
    response = client.post("/auth/login", data={"username": "nobody", "password": "whatever"})

    assert response.status_code == 401


def test_logout_invalidates_session(client):
    register(client, "dave", "pw")

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 200

    # session cookie has been cleared client-side, so a further authenticated
    # call has nothing to send and is rejected
    ping_response = client.get("/admin/ping")
    assert ping_response.status_code == 401


def test_admin_route_rejects_unauthenticated(client):
    response = client.get("/admin/ping")

    assert response.status_code == 401


def test_admin_route_rejects_non_admin_user(client):
    register(client, "eve", "pw")

    response = client.get("/admin/ping")

    assert response.status_code == 403


def test_admin_route_allows_admin_user(client):
    register(client, "frank", "pw")

    db = client.SessionLocal()
    try:
        user = db.query(User).filter_by(username="frank").first()
        user.is_admin = True
        db.commit()
    finally:
        db.close()

    response = client.get("/admin/ping")

    assert response.status_code == 200
    assert response.json() == {"pong": True, "admin": "frank"}
