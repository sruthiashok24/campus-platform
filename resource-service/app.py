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


@app.get("/health")
def health():
    return {"status": "ok", "service": "resource"}


@app.get("/api/resources")
@auth()
def list_resources():
    return jsonify(run(
        "SELECT r.id, r.name, r.type, r.quantity, "
        "(r.quantity - COALESCE(SUM(a.quantity), 0))::int AS available "
        "FROM resources r LEFT JOIN allocations a ON a.resource_id = r.id "
        "GROUP BY r.id ORDER BY r.id"
    ))


@app.post("/api/resources")
@auth("admin")
def add_resource():
    d = body()
    name = (d.get("name") or "").strip()
    rtype = (d.get("type") or "").strip()
    qty = to_int(d.get("quantity"), 1)
    if not name or not rtype or qty < 1:
        return {"error": "name, type and a quantity of at least 1 are required"}, 400
    row = run("INSERT INTO resources (name, type, quantity) VALUES (%s,%s,%s) RETURNING id, name, type, quantity",
              (name, rtype, qty), "one")
    row["available"] = row["quantity"]
    return jsonify(row), 201


@app.delete("/api/resources/<int:rid>")
@auth("admin")
def delete_resource(rid):
    run("DELETE FROM resources WHERE id=%s", (rid,), "none")
    return {"deleted": rid}


@app.get("/api/allocations")
@auth()
def list_allocations():
    event_id = to_int(request.args.get("event_id"))
    if not event_id:
        return {"error": "event_id is required"}, 400
    return jsonify(run(
        "SELECT a.id, a.event_id, a.resource_id, r.name, r.type, a.quantity "
        "FROM allocations a JOIN resources r ON r.id = a.resource_id WHERE a.event_id=%s ORDER BY a.id",
        (event_id,),
    ))


@app.post("/api/allocations")
@auth("admin")
def allocate():
    d = body()
    event_id, rid, qty = to_int(d.get("event_id")), to_int(d.get("resource_id")), to_int(d.get("quantity"), 1)
    if not event_id or not rid or qty < 1:
        return {"error": "event_id, resource_id and quantity are required"}, 400
    c = conn()
    try:
        with c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT quantity FROM resources WHERE id=%s FOR UPDATE", (rid,))
            res = cur.fetchone()
            if not res:
                return {"error": "resource not found"}, 404
            cur.execute("SELECT 1 FROM events WHERE id=%s", (event_id,))
            if not cur.fetchone():
                return {"error": "event not found"}, 404
            cur.execute("SELECT COALESCE(SUM(quantity), 0) AS used FROM allocations WHERE resource_id=%s", (rid,))
            available = res["quantity"] - int(cur.fetchone()["used"])
            if qty > available:
                return {"error": f"only {available} available"}, 409
            cur.execute(
                "INSERT INTO allocations (event_id, resource_id, quantity) VALUES (%s,%s,%s) "
                "ON CONFLICT (event_id, resource_id) DO UPDATE SET quantity = allocations.quantity + EXCLUDED.quantity "
                "RETURNING id",
                (event_id, rid, qty),
            )
            return jsonify(cur.fetchone()), 201
    finally:
        c.close()


@app.delete("/api/allocations/<int:aid>")
@auth("admin")
def remove_allocation(aid):
    run("DELETE FROM allocations WHERE id=%s", (aid,), "none")
    return {"deleted": aid}
