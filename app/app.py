import json
import os
import socket
import time
import uuid

import redis
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

APP_VERSION = os.getenv("APP_VERSION", "dev")

CHAT_KEY = "chat:messages"
CHAT_MAX_MESSAGES = 100
CHAT_MAX_TEXT = 500
CHAT_MAX_USERNAME = 50

FILE_KEY_PREFIX = "chat:file:"
FILE_TTL_SECONDS = 86400
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_FILE_TYPES = ("image/", "video/")


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
    attachment = data.get("attachment")
    if not username:
        return jsonify({"error": "username is required"}), 400
    if not text and not attachment:
        return jsonify({"error": "text or attachment is required"}), 400
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
    if attachment:
        if not isinstance(attachment, dict):
            return jsonify({"error": "attachment must be an object"}), 400
        atype = str(attachment.get("type", ""))
        url = str(attachment.get("url", ""))
        if atype not in ("image", "video") or not url.startswith("/api/files/"):
            return jsonify({"error": "invalid attachment"}), 400
        message["attachment"] = {
            "type": atype,
            "url": url,
            "name": str(attachment.get("name", ""))[:255],
        }
    r = get_redis()
    try:
        r.rpush(CHAT_KEY, json.dumps(message))
        r.ltrim(CHAT_KEY, -CHAT_MAX_MESSAGES, -1)
    except redis.RedisError as exc:
        return jsonify({"error": f"redis error: {exc}"}), 503
    return jsonify({"message": message}), 201


@app.route("/api/upload", methods=["POST"])
def upload_file():
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify({"error": "no file provided (form field 'file')"}), 400
    content_type = file.content_type or file.mimetype or ""
    if not content_type.startswith(ALLOWED_FILE_TYPES):
        return jsonify({"error": "only image/video files are allowed"}), 400
    data = file.read()
    if len(data) == 0:
        return jsonify({"error": "empty file"}), 400
    if len(data) > MAX_FILE_SIZE:
        return jsonify({"error": "file too large (max 10 MB)"}), 413

    file_id = uuid.uuid4().hex
    file_key = f"{FILE_KEY_PREFIX}{file_id}"
    r = get_redis()
    try:
        r.hset(file_key, mapping={"content_type": content_type, "data": data})
        r.expire(file_key, FILE_TTL_SECONDS)
    except redis.RedisError as exc:
        return jsonify({"error": f"redis error: {exc}"}), 503
    return (
        jsonify(
            {
                "url": f"/api/files/{file_id}",
                "type": "video" if content_type.startswith("video/") else "image",
                "name": file.filename,
                "size": len(data),
            }
        ),
        201,
    )


@app.route("/api/files/<file_id>")
def get_file(file_id):
    file_key = f"{FILE_KEY_PREFIX}{file_id}"
    r = get_redis()
    try:
        entry = r.hgetall(file_key)
    except redis.RedisError as exc:
        return jsonify({"error": f"redis error: {exc}"}), 503
    if not entry:
        return jsonify({"error": "file not found"}), 404
    content_type = (
        entry.get(b"content_type")
        or entry.get("content_type")
        or b"application/octet-stream"
    )
    if isinstance(content_type, bytes):
        content_type = content_type.decode("utf-8", "replace")
    data = entry.get(b"data") or entry.get("data") or b""
    return Response(data, content_type=content_type)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
