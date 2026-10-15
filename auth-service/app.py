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
from werkzeug.security import check_password_hash, generate_password_hash

ADMIN_CODE = os.getenv("ADMIN_CODE", "admin123")


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}


@app.post("/api/auth/register")
def register():
    d = body()
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    role = d.get("role", "student")
    if not name or "@" not in email:
        return {"error": "name and a valid email are required"}, 400
    if len(password) < 6:
        return {"error": "password must be at least 6 characters"}, 400
    if role not in ("student", "admin"):
        return {"error": "role must be student or admin"}, 400
    if role == "admin" and d.get("admin_code") != ADMIN_CODE:
        return {"error": "invalid admin access code"}, 403
    try:
        user = run(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s,%s,%s,%s) "
            "RETURNING id, name, email, role",
            (name, email, generate_password_hash(password, method="pbkdf2:sha256"), role),
            "one",
        )
    except psycopg2.errors.UniqueViolation:
        return {"error": "an account with this email already exists"}, 409
    return {"token": make_token(user), "user": user}, 201


@app.post("/api/auth/login")
def login():
    d = body()
    email = (d.get("email") or "").strip().lower()
    row = run("SELECT id, name, email, role, password_hash FROM users WHERE email=%s", (email,), "one")
    if not row or not check_password_hash(row["password_hash"], d.get("password") or ""):
        return {"error": "wrong email or password"}, 401
    wanted = d.get("role")
    if wanted and wanted != row["role"]:
        return {"error": f"this is a {row['role']} account, switch to the {row['role']} tab"}, 403
    user = {k: row[k] for k in ("id", "name", "email", "role")}
    return {"token": make_token(user), "user": user}


@app.get("/api/auth/me")
@auth()
def me():
    return jsonify(g.user)
