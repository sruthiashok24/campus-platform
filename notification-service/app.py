import os
from functools import wraps

import psycopg2
import psycopg2.errors
import psycopg2.extras
from flask import Flask, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

app = Flask(__name__)
_ser = URLSafeTimedSerializer(os.getenv("JWT_SECRET", "dev-secret-change-me"), salt="campus-auth")
TOKEN_MAX_AGE = 60 * 60 * 8  # 8 hours


def conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        dbname=os.getenv("DB_NAME", "campus"),
        user=os.getenv("DB_USER", "campus"),
        password=os.getenv("DB_PASSWORD", "campus"),
    )


def run(sql, args=(), fetch="all"):
    """Run one statement in its own transaction. fetch: all | one | none"""
    c = conn()
    try:
        with c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args)
            if fetch == "all":
                return cur.fetchall()
            if fetch == "one":
                return cur.fetchone()
    finally:
        c.close()


def make_token(user):
    return _ser.dumps({"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]})


def current_user():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    try:
        return _ser.loads(h[7:], max_age=TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def auth(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            u = current_user()
            if not u:
                return {"error": "please log in"}, 401
            if role and u["role"] != role:
                return {"error": "not allowed for your account type"}, 403
            g.user = u
            return f(*a, **k)
        return wrapper
    return deco


def body():
    return request.get_json(force=True, silent=True) or {}


def to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
import logging

logging.basicConfig(level=logging.INFO)


@app.get("/health")
def health():
    return {"status": "ok", "service": "notification"}


@app.post("/api/notify")  # internal only: not exposed through the frontend proxy
def notify():
    d = body()
    email, message = d.get("email"), d.get("message")
    if not email or not message:
        return {"error": "email and message are required"}, 400
    run("INSERT INTO notifications (user_email, message) VALUES (%s,%s)", (email, message), "none")
    app.logger.info("NOTIFICATION to=%s message=%s", email, message)
    return {"sent": True}, 201


@app.get("/api/notifications")
@auth()
def my_notifications():
    return jsonify(run(
        "SELECT id, message, created_at::text AS created_at FROM notifications "
        "WHERE user_email=%s ORDER BY id DESC LIMIT 50",
        (g.user["email"],),
    ))
