import os

import psycopg
from flask import Flask, jsonify, request
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]

app = Flask(__name__)

SEED_CLASSES = [
    ("Morning Yoga", "07:00", "Asha", 15),
    ("HIIT", "18:00", "Rahul", 20),
    ("Strength Training", "19:30", "Vikram", 12),
]


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    """Create tables and seed classes. Runs once at startup."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS classes (
                id       SERIAL PRIMARY KEY,
                name     TEXT UNIQUE NOT NULL,
                time     TEXT NOT NULL,
                trainer  TEXT NOT NULL,
                capacity INT  NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id          SERIAL PRIMARY KEY,
                class_id    INT  NOT NULL REFERENCES classes(id),
                member_name TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        for name, time, trainer, capacity in SEED_CLASSES:
            conn.execute(
                "INSERT INTO classes (name, time, trainer, capacity) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (name) DO NOTHING",
                (name, time, trainer, capacity),
            )


init_db()


@app.get("/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return jsonify(status="ok", database="up")
    except psycopg.Error:
        return jsonify(status="error", database="down"), 503


@app.get("/classes")
def list_classes():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.time, c.trainer, c.capacity,
                   COUNT(b.id)::int AS booked
            FROM classes c
            LEFT JOIN bookings b ON b.class_id = c.id
            GROUP BY c.id
            ORDER BY c.id
            """
        ).fetchall()
    return jsonify(rows)


@app.get("/bookings")
def list_bookings():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT b.id, b.member_name, c.name AS class_name, c.time, b.created_at
            FROM bookings b
            JOIN classes c ON c.id = b.class_id
            ORDER BY b.created_at DESC
            """
        ).fetchall()
    return jsonify(rows)


@app.post("/bookings")
def create_booking():
    data = request.get_json(silent=True) or {}
    class_id = data.get("class_id")
    member_name = str(data.get("member_name") or "").strip()

    if not isinstance(class_id, int) or not member_name:
        return jsonify(error="class_id (number) and member_name are required"), 400

    with get_conn() as conn:
        # Lock the class row so two people can't take the last spot at the same time
        cls = conn.execute(
            "SELECT id, capacity FROM classes WHERE id = %s FOR UPDATE", (class_id,)
        ).fetchone()
        if cls is None:
            return jsonify(error="class not found"), 404

        booked = conn.execute(
            "SELECT COUNT(*)::int AS n FROM bookings WHERE class_id = %s", (class_id,)
        ).fetchone()["n"]
        if booked >= cls["capacity"]:
            return jsonify(error="class is full"), 409

        booking = conn.execute(
            "INSERT INTO bookings (class_id, member_name) VALUES (%s, %s) "
            "RETURNING id, class_id, member_name, created_at",
            (class_id, member_name),
        ).fetchone()

    return jsonify(booking), 201
