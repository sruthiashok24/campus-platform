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
import hashlib
import time

import requests

EVENT_URL = os.getenv("EVENT_SERVICE_URL", "http://event-service:8000")
NOTIFY_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8000")


@app.get("/health")
def health():
    return {"status": "ok", "service": "registration"}


@app.post("/api/register")
@auth("student")
def register():
    event_id = to_int(body().get("event_id"))
    if not event_id:
        return {"error": "event_id is required"}, 400

    # service-to-service call 1: ask the event service about the event
    r = requests.get(f"{EVENT_URL}/api/events/{event_id}", timeout=5)
    if r.status_code != 200:
        return {"error": "event not found"}, 404
    event = r.json()

    c = conn()
    try:
        with c, c.cursor() as cur:
            cur.execute("SELECT id FROM events WHERE id=%s FOR UPDATE", (event_id,))  # serialise seat counting
            cur.execute("SELECT COUNT(*) FROM registrations WHERE event_id=%s", (event_id,))
            if cur.fetchone()[0] >= event["capacity"]:
                return {"error": "this event is full"}, 409
            cur.execute(
                "INSERT INTO registrations (user_id, event_id) VALUES (%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING id",
                (g.user["id"], event_id),
            )
            if not cur.fetchone():
                return {"error": "you are already registered for this event"}, 409
    finally:
        c.close()

    # service-to-service call 2: notification (registration still succeeds if it is down)
    try:
        requests.post(
            f"{NOTIFY_URL}/api/notify",
            json={"email": g.user["email"], "message": f"You are registered for {event['title']} on {event['event_date']}"},
            timeout=3,
        )
    except requests.RequestException:
        pass
    return {"registered": True, "event": event["title"]}, 201


@app.delete("/api/register/<int:event_id>")
@auth("student")
def cancel(event_id):
    run("DELETE FROM registrations WHERE user_id=%s AND event_id=%s", (g.user["id"], event_id), "none")
    return {"cancelled": event_id}


@app.get("/api/registrations/mine")
@auth("student")
def my_registrations():
    return jsonify(run(
        "SELECT r.id, e.id AS event_id, e.title, e.category, e.venue, e.event_date::text AS event_date, "
        "r.created_at::text AS registered_at "
        "FROM registrations r JOIN events e ON e.id = r.event_id "
        "WHERE r.user_id=%s ORDER BY e.event_date",
        (g.user["id"],),
    ))


@app.get("/api/registrations")
@auth("admin")
def attendees():
    event_id = to_int(request.args.get("event_id"))
    if not event_id:
        return {"error": "event_id is required"}, 400
    return jsonify(run(
        "SELECT r.id, u.name, u.email, r.created_at::text AS registered_at "
        "FROM registrations r JOIN users u ON u.id = r.user_id WHERE r.event_id=%s ORDER BY r.id",
        (event_id,),
    ))


@app.get("/api/stress")
def stress():
    """CPU-heavy endpoint for the autoscaling demo: /api/stress?ms=200"""
    ms = min(to_int(request.args.get("ms"), 100), 2000)
    end = time.time() + ms / 1000
    h = b"x"
    while time.time() < end:
        h = hashlib.sha256(h).digest()
    return {"burned_ms": ms}
