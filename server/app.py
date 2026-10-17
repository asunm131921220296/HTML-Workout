import os
import re
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, current_app, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash


RATE_PER_DELIVERY = 15
EMAIL_PATTERN = re.compile(
    r"[^@\s]{1,64}@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}"
)


def normalize_email(value):
    if not isinstance(value, str):
        return ""
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        return ""
    return email


def get_db():
    if "db" not in g:
        database_path = current_app.config["DATABASE"]
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def initialize_database(app):
    with app.app_context():
        database = get_db()
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'partner'
                    CHECK (role IN ('admin', 'partner')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                attendance_date TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT,
                pickup_count INTEGER NOT NULL DEFAULT 0 CHECK (pickup_count >= 0),
                completed_count INTEGER NOT NULL DEFAULT 0
                    CHECK (completed_count >= 0),
                UNIQUE (user_id, attendance_date)
            );
            CREATE INDEX IF NOT EXISTS attendance_date_idx
                ON attendance(attendance_date);
            """
        )
        user_columns = {
            row["name"] for row in database.execute("PRAGMA table_info(users)").fetchall()
        }
        if "email" not in user_columns:
            database.execute("ALTER TABLE users ADD COLUMN email TEXT")
        database.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique_idx ON users(email)"
        )

        username = app.config["ADMIN_USERNAME"].strip().lower()
        admin_email = normalize_email(app.config["ADMIN_EMAIL"])
        password = app.config["ADMIN_PASSWORD"]
        if not admin_email:
            raise ValueError("Set ADMIN_EMAIL to a valid email address for the administrator account.")
        existing_account = database.execute(
            "SELECT id, role, email FROM users WHERE email = ?",
            (admin_email,),
        ).fetchone()
        if existing_account is None:
            existing_account = database.execute(
                "SELECT id, role, email FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if existing_account and existing_account["role"] != "admin":
            raise ValueError("ADMIN_EMAIL or ADMIN_USERNAME is already assigned to a delivery partner.")
        if not existing_account:
            database.execute(
                """
                INSERT INTO users (username, email, full_name, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, 'admin', ?)
                """,
                (
                    username,
                    admin_email,
                    "Administrator",
                    generate_password_hash(password),
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
        elif existing_account["email"] is None:
            database.execute(
                "UPDATE users SET email = ? WHERE id = ?",
                (admin_email, existing_account["id"]),
            )
        database.commit()


def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return get_db().execute(
        "SELECT id, username, email, full_name, role FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify(error="Please sign in to continue."), 401
        g.user = user
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            return jsonify(error="Administrator access is required."), 403
        return view(*args, **kwargs)

    return wrapped


def csrf_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = session.get("csrf_token")
        provided = request.headers.get("X-CSRF-Token")
        if not expected or not provided or not secrets.compare_digest(expected, provided):
            return jsonify(error="Your session token is missing or expired. Refresh and try again."), 400
        return view(*args, **kwargs)

    return wrapped


def serialize_user(user):
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }


def serialize_attendance(row):
    return {
        "id": row["id"],
        "date": row["attendance_date"],
        "check_in": row["check_in"],
        "check_out": row["check_out"],
        "pickup_count": row["pickup_count"],
        "completed_count": row["completed_count"],
        "earnings": row["completed_count"] * RATE_PER_DELIVERY,
    }


def parse_report_dates():
    today = date.today()
    start_default = today.replace(day=1).isoformat()
    start_value = request.args.get("from", start_default)
    end_value = request.args.get("to", today.isoformat())
    try:
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
    except ValueError:
        return None, None, (jsonify(error="Report dates must use YYYY-MM-DD format."), 400)
    if start > end:
        return None, None, (jsonify(error="The start date must be on or before the end date."), 400)
    return start.isoformat(), end.isoformat(), None


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    instance_path = Path(__file__).resolve().parent / "instance"
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get("DATABASE_PATH", str(instance_path / "attendance.sqlite3")),
        FRONTEND_DIST=str(Path(__file__).resolve().parent.parent / "frontend" / "dist"),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL", "admin@example.com"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if (
        not app.config["ADMIN_USERNAME"].strip()
        or not app.config["ADMIN_PASSWORD"]
        or len(app.config["ADMIN_PASSWORD"]) < 10
    ):
        raise ValueError("Set ADMIN_EMAIL, ADMIN_USERNAME, and an ADMIN_PASSWORD of at least 10 characters before starting the API.")

    app.teardown_appcontext(close_db)
    initialize_database(app)

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        if path.startswith("api/"):
            abort(404)
        frontend_dist = Path(current_app.config["FRONTEND_DIST"])
        if not (frontend_dist / "index.html").is_file():
            return jsonify(error="The frontend has not been built yet. See SETUP.md for local development instructions."), 503
        requested_file = frontend_dist / path
        if path and requested_file.is_file():
            return send_from_directory(frontend_dist, path)
        if path and "." in Path(path).name:
            abort(404)
        return send_from_directory(frontend_dist, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/auth/csrf")
    def csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return jsonify(csrf_token=token)

    @app.post("/api/auth/register")
    @csrf_required
    def register():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="A JSON object is required."), 400
        email = normalize_email(data.get("email"))
        full_name_value = data.get("full_name")
        full_name = full_name_value.strip() if isinstance(full_name_value, str) else ""
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")
        if not email:
            return jsonify(error="Enter a valid email address."), 400
        if not full_name or len(full_name) > 100:
            return jsonify(error="Enter your name (up to 100 characters)."), 400
        if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
            return jsonify(error="Your password must be between 10 and 128 characters."), 400
        if not isinstance(confirm_password, str) or password != confirm_password:
            return jsonify(error="Passwords do not match."), 400
        database = get_db()
        try:
            cursor = database.execute(
                """
                INSERT INTO users (username, email, full_name, password_hash, role, created_at)
                VALUES (?, ?, ?, ?, 'partner', ?)
                """,
                (
                    email,
                    email,
                    full_name,
                    generate_password_hash(password),
                    datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
            database.commit()
        except sqlite3.IntegrityError:
            return jsonify(error="That email address is already registered."), 409
        session.clear()
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(
            message="Your account has been created. Please sign in.",
            email=email,
            csrf_token=session["csrf_token"],
        ), 201

    @app.post("/api/auth/login")
    @csrf_required
    def login():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="A JSON object is required."), 400
        email_value = data.get("email")
        email = normalize_email(email_value)
        legacy_username = (
            email_value.strip().lower()
            if isinstance(email_value, str) and not email
            else ""
        )
        password = data.get("password", "")
        user = get_db().execute(
            """
            SELECT id, username, email, full_name, password_hash, role
            FROM users
            WHERE email = ? OR (email IS NULL AND username = ?)
            ORDER BY CASE WHEN email = ? THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (email, legacy_username, email),
        ).fetchone()
        if user is None or not isinstance(password, str) or not check_password_hash(user["password_hash"], password):
            return jsonify(error="Incorrect email or username, or password."), 401
        session.clear()
        session["user_id"] = user["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        return jsonify(user=serialize_user(user), csrf_token=session["csrf_token"])

    @app.post("/api/auth/logout")
    @csrf_required
    @login_required
    def logout():
        session.clear()
        return jsonify(message="Signed out.")

    @app.get("/api/auth/me")
    @login_required
    def me():
        return jsonify(user=serialize_user(g.user))

    @app.get("/api/dashboard")
    @login_required
    def dashboard():
        today = date.today().isoformat()
        database = get_db()
        today_row = database.execute(
            "SELECT * FROM attendance WHERE user_id = ? AND attendance_date = ?",
            (g.user["id"], today),
        ).fetchone()
        totals = database.execute(
            """
            SELECT COUNT(*) AS attendance_days,
                   COALESCE(SUM(completed_count), 0) AS completed_count,
                   COALESCE(SUM(pickup_count), 0) AS pickup_count
            FROM attendance WHERE user_id = ?
            """,
            (g.user["id"],),
        ).fetchone()
        history = database.execute(
            """
            SELECT * FROM attendance WHERE user_id = ?
            ORDER BY attendance_date DESC LIMIT 9
            """,
            (g.user["id"],),
        ).fetchall()
        today_data = serialize_attendance(today_row) if today_row else None
        lifetime_completed = totals["completed_count"]
        return jsonify(
            today=today_data,
            today_earnings=today_data["earnings"] if today_data else 0,
            lifetime_earnings=lifetime_completed * RATE_PER_DELIVERY,
            attendance_days=totals["attendance_days"],
            lifetime_completed=lifetime_completed,
            lifetime_pickups=totals["pickup_count"],
            rate_per_delivery=RATE_PER_DELIVERY,
            history=[serialize_attendance(row) for row in history[:8]],
            history_has_more=len(history) > 8,
        )

    @app.get("/api/attendance/history")
    @login_required
    def attendance_history():
        try:
            limit = int(request.args.get("limit", "20"))
            offset = int(request.args.get("offset", "0"))
        except ValueError:
            return jsonify(error="History limit and offset must be whole numbers."), 400
        if not 1 <= limit <= 100 or offset < 0:
            return jsonify(error="History limit must be 1–100 and offset cannot be negative."), 400
        database = get_db()
        total = database.execute(
            "SELECT COUNT(*) AS total FROM attendance WHERE user_id = ?",
            (g.user["id"],),
        ).fetchone()["total"]
        rows = get_db().execute(
            """
            SELECT * FROM attendance WHERE user_id = ?
            ORDER BY attendance_date DESC LIMIT ? OFFSET ?
            """,
            (g.user["id"], limit, offset),
        ).fetchall()
        next_offset = offset + len(rows)
        return jsonify(
            history=[serialize_attendance(row) for row in rows],
            has_more=next_offset < total,
            next_offset=next_offset,
        )

    @app.post("/api/attendance/check-in")
    @csrf_required
    @login_required
    def check_in():
        database = get_db()
        today = date.today().isoformat()
        existing = database.execute(
            "SELECT id FROM attendance WHERE user_id = ? AND attendance_date = ?",
            (g.user["id"], today),
        ).fetchone()
        if existing:
            return jsonify(error="You have already checked in today."), 409
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        database.execute(
            """
            INSERT INTO attendance (user_id, attendance_date, check_in)
            VALUES (?, ?, ?)
            """,
            (g.user["id"], today, now),
        )
        database.commit()
        return jsonify(message="Checked in successfully.", check_in=now), 201

    @app.post("/api/attendance/check-out")
    @csrf_required
    @login_required
    def check_out():
        database = get_db()
        today = date.today().isoformat()
        row = database.execute(
            "SELECT * FROM attendance WHERE user_id = ? AND attendance_date = ?",
            (g.user["id"], today),
        ).fetchone()
        if row is None:
            return jsonify(error="Check in before checking out."), 409
        if row["check_out"]:
            return jsonify(error="You have already checked out today."), 409
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        database.execute("UPDATE attendance SET check_out = ? WHERE id = ?", (now, row["id"]))
        database.commit()
        return jsonify(message="Checked out successfully.", check_out=now)

    @app.put("/api/attendance/today")
    @csrf_required
    @login_required
    def update_today_counts():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="A JSON object is required."), 400
        counts = {}
        for key in ("pickup_count", "completed_count"):
            value = data.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10000:
                return jsonify(error=f"{key.replace('_', ' ').capitalize()} must be a whole number from 0 to 10,000."), 400
            counts[key] = value
        database = get_db()
        row = database.execute(
            "SELECT * FROM attendance WHERE user_id = ? AND attendance_date = ?",
            (g.user["id"], date.today().isoformat()),
        ).fetchone()
        if row is None:
            return jsonify(error="Check in before recording today's deliveries."), 409
        if row["check_out"]:
            return jsonify(error="Today's delivery totals are locked after checkout."), 409
        database.execute(
            """
            UPDATE attendance SET pickup_count = ?, completed_count = ? WHERE id = ?
            """,
            (counts["pickup_count"], counts["completed_count"], row["id"]),
        )
        database.commit()
        updated = database.execute("SELECT * FROM attendance WHERE id = ?", (row["id"],)).fetchone()
        return jsonify(attendance=serialize_attendance(updated))

    @app.get("/api/admin/reports")
    @admin_required
    def admin_reports():
        start, end, error = parse_report_dates()
        if error:
            return error
        database = get_db()
        partners = database.execute(
            """
            SELECT u.id, u.username, u.email, u.full_name,
                   COUNT(a.id) AS attendance_days,
                   COALESCE(SUM(a.pickup_count), 0) AS pickup_count,
                   COALESCE(SUM(a.completed_count), 0) AS completed_count
            FROM users u
            LEFT JOIN attendance a ON a.user_id = u.id
                AND a.attendance_date BETWEEN ? AND ?
            WHERE u.role = 'partner'
            GROUP BY u.id
            ORDER BY u.full_name COLLATE NOCASE
            """,
            (start, end),
        ).fetchall()
        daily_rows = database.execute(
            """
            SELECT attendance_date, SUM(completed_count) AS completed_count,
                   SUM(pickup_count) AS pickup_count
            FROM attendance
            WHERE attendance_date BETWEEN ? AND ?
            GROUP BY attendance_date ORDER BY attendance_date
            """,
            (start, end),
        ).fetchall()
        report_partners = [
            {
                "id": row["id"],
                "email": row["email"],
                "legacy_username": row["username"] if row["email"] is None else None,
                "full_name": row["full_name"],
                "attendance_days": row["attendance_days"],
                "pickup_count": row["pickup_count"],
                "completed_count": row["completed_count"],
                "earnings": row["completed_count"] * RATE_PER_DELIVERY,
            }
            for row in partners
        ]
        completed = sum(partner["completed_count"] for partner in report_partners)
        pickups = sum(partner["pickup_count"] for partner in report_partners)
        return jsonify(
            from_date=start,
            to_date=end,
            rate_per_delivery=RATE_PER_DELIVERY,
            summary={
                "partner_count": len(report_partners),
                "attendance_days": sum(partner["attendance_days"] for partner in report_partners),
                "pickup_count": pickups,
                "completed_count": completed,
                "earnings": completed * RATE_PER_DELIVERY,
            },
            partners=report_partners,
            daily=[
                {
                    "date": row["attendance_date"],
                    "completed_count": row["completed_count"],
                    "pickup_count": row["pickup_count"],
                    "earnings": row["completed_count"] * RATE_PER_DELIVERY,
                }
                for row in daily_rows
            ],
        )

    @app.get("/api/admin/reports/<int:partner_id>")
    @admin_required
    def individual_report(partner_id):
        start, end, error = parse_report_dates()
        if error:
            return error
        database = get_db()
        partner = database.execute(
            "SELECT id, username, email, full_name, role FROM users WHERE id = ? AND role = 'partner'",
            (partner_id,),
        ).fetchone()
        if partner is None:
            return jsonify(error="Delivery partner not found."), 404
        rows = database.execute(
            """
            SELECT * FROM attendance WHERE user_id = ?
                AND attendance_date BETWEEN ? AND ?
            ORDER BY attendance_date DESC
            """,
            (partner_id, start, end),
        ).fetchall()
        history = [serialize_attendance(row) for row in rows]
        completed = sum(row["completed_count"] for row in history)
        return jsonify(
            partner=serialize_user(partner),
            from_date=start,
            to_date=end,
            summary={
                "attendance_days": len(history),
                "pickup_count": sum(row["pickup_count"] for row in history),
                "completed_count": completed,
                "earnings": completed * RATE_PER_DELIVERY,
            },
            history=history,
        )

    return app


if __name__ == "__main__":
    create_app().run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
    )
