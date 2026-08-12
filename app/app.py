import os
import socket

import redis
from flask import Flask, jsonify

app = Flask(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

APP_VERSION = os.getenv("APP_VERSION", "dev")


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
