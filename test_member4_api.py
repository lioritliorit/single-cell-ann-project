import os
import tempfile


def build_client():
    temp_dir = tempfile.TemporaryDirectory()
    os.environ["AUTH_DB_PATH"] = os.path.join(temp_dir.name, "auth.db")
    os.environ["ADMIN_USERNAME"] = "admin"
    os.environ["ADMIN_PASSWORD"] = "admin123"

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), temp_dir


def assert_status(response, status_code):
    assert response.status_code == status_code, response.get_json()


def main() -> None:
    client, temp_dir = build_client()
    try:
        response = client.get("/api/health")
        assert_status(response, 200)
        assert response.get_json()["auth"]["enabled"] is True

        response = client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "alice123", "email": "alice@example.com"},
        )
        assert_status(response, 201)
        assert response.get_json()["user"]["role"] == "user"

        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "alice123"},
        )
        assert_status(response, 200)
        user_token = response.get_json()["token"]

        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {user_token}"})
        assert_status(response, 200)
        assert response.get_json()["user"]["username"] == "alice"

        response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {user_token}"})
        assert_status(response, 403)

        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert_status(response, 200)
        admin_token = response.get_json()["token"]

        response = client.get("/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"})
        assert_status(response, 200)
        usernames = {user["username"] for user in response.get_json()["users"]}
        assert {"admin", "alice"} <= usernames

        response = client.get("/api/datasets")
        assert_status(response, 200)
        datasets = response.get_json()["datasets"]
        assert any(dataset["id"] == "default" for dataset in datasets)

        response = client.put(
            "/api/admin/dataset-policies/default",
            json={"visibility": "public"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert_status(response, 200)
        assert response.get_json()["policy"]["visibility"] == "public"

        response = client.post(
            "/api/rag/query",
            json={"question": "Find hepatocyte cells from liver fibrosis", "k": 3},
        )
        assert_status(response, 200)
        parsed = response.get_json()["parsed_filters"]
        assert parsed["cell_type"] == "hepatocyte"
        assert parsed["disease"] == "fibrosis"

        response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {user_token}"})
        assert_status(response, 200)
    finally:
        temp_dir.cleanup()

    print("member4 API tests passed")


if __name__ == "__main__":
    main()
