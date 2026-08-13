import json
import os
import socket
import time

import redis
from flask import Flask, jsonify, request

app = Flask(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

APP_VERSION = os.getenv("APP_VERSION", "dev")

CHAT_KEY = "chat:messages"
CHAT_MAX_MESSAGES = 100
CHAT_MAX_TEXT = 500
CHAT_MAX_USERNAME = 50


def get_redis():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD or None,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


@app.route("/")
def index():
    r = get_redis()
    try:
        count = r.incr("visits")
        redis_status = "connected"
    except redis.RedisError as exc:
        count = None
        redis_status = f"error: {exc}"
    return jsonify(
        {
            "service": "demo-backend",
            "version": APP_VERSION,
            "hostname": socket.gethostname(),
            "visits": count,
            "redis": redis_status,
        }
    )


@app.route("/health")
def health():
    r = get_redis()
    try:
        r.ping()
        status = 200
        db = "connected"
    except redis.RedisError as exc:
        status = 503
        db = f"unreachable: {exc}"
    return (
        jsonify({"status": "healthy" if status == 200 else "unhealthy", "redis": db}),
        status,
    )


@app.route("/info")
def info():
    return jsonify(
        {
            "version": APP_VERSION,
            "redis_host": REDIS_HOST,
            "redis_port": REDIS_PORT,
        }
    )


@app.route("/api/messages", methods=["GET"])
def list_messages():
    r = get_redis()
    try:
        raw = r.lrange(CHAT_KEY, 0, -1)
    except redis.RedisError as exc:
        return jsonify({"error": f"redis error: {exc}"}), 503
    messages = []
    for entry in raw:
        try:
            messages.append(json.loads(entry))
        except (TypeError, ValueError):
            continue
    return jsonify({"messages": messages})


@app.route("/api/messages", methods=["POST"])
def add_message():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    text = str(data.get("text", "")).strip()
    if not username:
        return jsonify({"error": "username is required"}), 400
    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(username) > CHAT_MAX_USERNAME:
        username = username[:CHAT_MAX_USERNAME]
    if len(text) > CHAT_MAX_TEXT:
        text = text[:CHAT_MAX_TEXT]
    message = {
        "id": f"{int(time.time() * 1000)}-{socket.gethostname()}",
        "username": username,
        "text": text,
        "ts": int(time.time()),
    }
    r = get_redis()
    try:
        r.rpush(CHAT_KEY, json.dumps(message))
        r.ltrim(CHAT_KEY, -CHAT_MAX_MESSAGES, -1)
    except redis.RedisError as exc:
        return jsonify({"error": f"redis error: {exc}"}), 503
    return jsonify({"message": message}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
