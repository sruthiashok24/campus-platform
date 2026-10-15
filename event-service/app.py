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

EVENT_SELECT = (
    "SELECT e.id, e.title, e.description, e.category, e.venue, e.event_date::text AS event_date, "
    "e.capacity, (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id)::int AS registered "
    "FROM events e"
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "event"}


@app.get("/api/events")
def list_events():
    return jsonify(run(EVENT_SELECT + " ORDER BY e.event_date, e.id"))


@app.get("/api/events/<int:event_id>")
def get_event(event_id):
    row = run(EVENT_SELECT + " WHERE e.id=%s", (event_id,), "one")
    if not row:
        return {"error": "event not found"}, 404
    return jsonify(row)


@app.post("/api/events")
@auth("admin")
def create_event():
    d = body()
    title = (d.get("title") or "").strip()
    date = d.get("event_date")
    capacity = to_int(d.get("capacity"), 100)
    if not title or not date:
        return {"error": "title and date are required"}, 400
    if capacity < 1:
        return {"error": "capacity must be at least 1"}, 400
    try:
        row = run(
            "INSERT INTO events (title, description, category, venue, event_date, capacity, created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (title, d.get("description", ""), d.get("category") or "Event", d.get("venue", ""), date, capacity, g.user["id"]),
            "one",
        )
    except psycopg2.errors.InvalidDatetimeFormat:
        return {"error": "invalid date"}, 400
    return jsonify(run(EVENT_SELECT + " WHERE e.id=%s", (row["id"],), "one")), 201


@app.delete("/api/events/<int:event_id>")
@auth("admin")
def delete_event(event_id):
    run("DELETE FROM events WHERE id=%s", (event_id,), "none")
    return {"deleted": event_id}
