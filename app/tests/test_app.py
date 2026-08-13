import importlib.util
import pathlib
import sys

import fakeredis
import pytest

APP_PATH = pathlib.Path(__file__).resolve().parent.parent / "app.py"
spec = importlib.util.spec_from_file_location("chat_app", APP_PATH)
chat_app = importlib.util.module_from_spec(spec)
sys.modules["chat_app"] = chat_app
spec.loader.exec_module(chat_app)


@pytest.fixture()
def client(monkeypatch):
    server = fakeredis.FakeServer()
    chat_app.get_redis = lambda: fakeredis.FakeRedis(
        server=server, decode_responses=True
    )
    chat_app.app.config["TESTING"] = True
    return chat_app.app.test_client()


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.get_json()["service"] == "demo-backend"


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "healthy"


def test_post_and_list_messages(client):
    post = client.post("/api/messages", json={"username": "alice", "text": "hello"})
    assert post.status_code == 201
    saved = post.get_json()["message"]
    assert saved["username"] == "alice"
    assert saved["text"] == "hello"

    resp = client.get("/api/messages")
    assert resp.status_code == 200
    messages = resp.get_json()["messages"]
    assert len(messages) == 1
    assert messages[0]["text"] == "hello"


def test_post_message_validation(client):
    assert client.post("/api/messages", json={"text": "no user"}).status_code == 400
    assert client.post("/api/messages", json={"username": "u", "text": ""}).status_code == 400


def test_chat_limits(client):
    long_text = "x" * 1000
    resp = client.post(
        "/api/messages", json={"username": "u" * 200, "text": long_text}
    )
    assert resp.status_code == 201
    saved = resp.get_json()["message"]
    assert len(saved["username"]) == chat_app.CHAT_MAX_USERNAME
    assert len(saved["text"]) == chat_app.CHAT_MAX_TEXT
