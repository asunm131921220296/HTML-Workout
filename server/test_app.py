import tempfile
import unittest
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from app import create_app, normalize_email
from werkzeug.security import generate_password_hash


class AttendanceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.frontend_dist = Path(self.temp_dir.name) / "frontend"
        self.frontend_dist.mkdir()
        (self.frontend_dist / "index.html").write_text(
            "<!doctype html><title>Relay test</title>", encoding="utf-8"
        )
        (self.frontend_dist / "assets").mkdir()
        (self.frontend_dist / "assets" / "app.js").write_text(
            "console.log('relay');", encoding="utf-8"
        )
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite3"),
                "FRONTEND_DIST": str(self.frontend_dist),
                "ADMIN_USERNAME": "admin",
                "ADMIN_EMAIL": "admin@example.com",
                "ADMIN_PASSWORD": "TestAdmin123!",
            }
        )
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/auth/csrf").get_json()["csrf_token"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def headers(self):
        return {"X-CSRF-Token": self.csrf}

    def register_partner(self, email="rider@example.com"):
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "full_name": "Ravi Kumar",
                "password": "RiderPass123!",
                "confirm_password": "RiderPass123!",
            },
            headers=self.headers(),
        )
        if response.status_code == 201:
            self.csrf = response.get_json()["csrf_token"]
            signed_in = self.client.post(
                "/api/auth/login",
                json={"email": email, "password": "RiderPass123!"},
                headers=self.headers(),
            )
            self.csrf = signed_in.get_json()["csrf_token"]
        return response

    def login_admin(self):
        response = self.client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "TestAdmin123!"},
            headers=self.headers(),
        )
        self.csrf = response.get_json()["csrf_token"]
        return response

    def test_partner_attendance_and_earnings_use_completed_deliveries_only(self):
        registration = self.register_partner()
        self.assertEqual(registration.status_code, 201)
        self.assertEqual(
            self.client.post("/api/attendance/check-in", headers=self.headers()).status_code,
            201,
        )
        saved = self.client.put(
            "/api/attendance/today",
            json={"pickup_count": 12, "completed_count": 7},
            headers=self.headers(),
        )
        self.assertEqual(saved.status_code, 200)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["today_earnings"], 105)
        self.assertEqual(dashboard["lifetime_earnings"], 105)
        self.assertEqual(dashboard["today"]["pickup_count"], 12)
        self.assertEqual(dashboard["today"]["completed_count"], 7)
        self.assertEqual(
            self.client.post("/api/attendance/check-out", headers=self.headers()).status_code,
            200,
        )
        locked = self.client.put(
            "/api/attendance/today",
            json={"pickup_count": 12, "completed_count": 8},
            headers=self.headers(),
        )
        self.assertEqual(locked.status_code, 409)

    def test_validation_and_duplicate_attendance_are_rejected(self):
        self.register_partner()
        self.assertEqual(
            self.client.put(
                "/api/attendance/today",
                json={"pickup_count": -1, "completed_count": 3},
                headers=self.headers(),
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post("/api/attendance/check-in", headers=self.headers()).status_code,
            201,
        )
        self.assertEqual(
            self.client.post("/api/attendance/check-in", headers=self.headers()).status_code,
            409,
        )

    def test_admin_can_view_overall_and_individual_reports(self):
        self.register_partner()
        self.client.post("/api/attendance/check-in", headers=self.headers())
        self.client.put(
            "/api/attendance/today",
            json={"pickup_count": 9, "completed_count": 4},
            headers=self.headers(),
        )
        self.client.post("/api/auth/logout", headers=self.headers())
        self.csrf = self.client.get("/api/auth/csrf").get_json()["csrf_token"]
        self.assertEqual(self.login_admin().status_code, 200)

        query = f"from={date.today().isoformat()}&to={date.today().isoformat()}"
        overall = self.client.get(f"/api/admin/reports?{query}")
        self.assertEqual(overall.status_code, 200)
        self.assertEqual(overall.get_json()["summary"]["earnings"], 60)
        self.assertEqual(overall.get_json()["summary"]["pickup_count"], 9)

        partner_id = overall.get_json()["partners"][0]["id"]
        individual = self.client.get(f"/api/admin/reports/{partner_id}?{query}")
        self.assertEqual(individual.status_code, 200)
        self.assertEqual(individual.get_json()["history"][0]["earnings"], 60)

    def test_partner_cannot_access_admin_reports_and_login_requires_csrf(self):
        self.register_partner()
        self.client.post("/api/auth/logout", headers=self.headers())
        self.csrf = self.client.get("/api/auth/csrf").get_json()["csrf_token"]
        self.client.post(
            "/api/auth/login",
            json={"email": "rider@example.com", "password": "RiderPass123!"},
            headers=self.headers(),
        )
        self.assertEqual(self.client.get("/api/admin/reports").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": "incorrect"},
            ).status_code,
            400,
        )

    def test_attendance_history_is_paginated_without_dropping_older_days(self):
        self.register_partner()
        lookup = sqlite3.connect(self.app.config["DATABASE"])
        try:
            partner_id = lookup.execute(
                "SELECT id FROM users WHERE email = 'rider@example.com'"
            ).fetchone()[0]
        finally:
            lookup.close()
        database = sqlite3.connect(self.app.config["DATABASE"])
        try:
            for days_ago in range(1, 10):
                database.execute(
                    """
                    INSERT INTO attendance (user_id, attendance_date, check_in, completed_count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        partner_id,
                        (date.today() - timedelta(days=days_ago)).isoformat(),
                        "2026-01-01T09:00:00+05:30",
                        days_ago,
                    ),
                )
            database.commit()
        finally:
            database.close()
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(len(dashboard["history"]), 8)
        self.assertTrue(dashboard["history_has_more"])
        page = self.client.get("/api/attendance/history?limit=2&offset=8").get_json()
        self.assertEqual(len(page["history"]), 1)
        self.assertFalse(page["has_more"])
        self.assertEqual(page["history"][0]["completed_count"], 9)
        self.assertEqual(
            self.client.get("/api/attendance/history?limit=101").status_code,
            400,
        )

    def test_email_validation_and_duplicate_registration(self):
        invalid = self.client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "full_name": "Ravi Kumar",
                "password": "RiderPass123!",
                "confirm_password": "RiderPass123!",
            },
            headers=self.headers(),
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(normalize_email(" Rider@Example.COM "), "rider@example.com")
        self.assertEqual(self.register_partner().status_code, 201)
        duplicate = self.client.post(
            "/api/auth/register",
            json={
                "email": "RIDER@example.com",
                "full_name": "Another Rider",
                "password": "RiderPass123!",
                "confirm_password": "RiderPass123!",
            },
            headers=self.headers(),
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_registration_rejects_password_confirmation_mismatch(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": "rider@example.com",
                "full_name": "Ravi Kumar",
                "password": "RiderPass123!",
                "confirm_password": "DifferentPass123!",
            },
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Passwords do not match.")

    def test_registration_does_not_sign_in_automatically(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": "rider@example.com",
                "full_name": "Ravi Kumar",
                "password": "RiderPass123!",
                "confirm_password": "RiderPass123!",
            },
            headers=self.headers(),
        )
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("user", response.get_json())
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_frontend_is_served_and_missing_api_routes_do_not_fall_back_to_html(self):
        for path, expected in (
            ("/", b"Relay test"),
            ("/assets/app.js", b"console.log"),
            ("/reports", b"Relay test"),
        ):
            response = self.client.get(path)
            try:
                self.assertEqual(response.status_code, 200)
                self.assertIn(expected, response.get_data())
            finally:
                response.close()
        self.assertEqual(self.client.get("/api/not-a-route").status_code, 404)
        self.assertEqual(self.client.get("/assets/missing.js").status_code, 404)

    def test_existing_database_migrates_without_losing_accounts_or_attendance(self):
        database_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        database = sqlite3.connect(database_path)
        database.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'partner',
                created_at TEXT NOT NULL
            );
            CREATE TABLE attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                attendance_date TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT,
                pickup_count INTEGER NOT NULL DEFAULT 0,
                completed_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE (user_id, attendance_date)
            );
            INSERT INTO users (id, username, full_name, password_hash, role, created_at)
            VALUES (1, 'admin', 'Administrator', 'unused', 'admin', '2026-01-01');
            """
        )
        database.execute(
            """
            INSERT INTO users (id, username, full_name, password_hash, role, created_at)
            VALUES (2, 'legacy_rider', 'Legacy Rider', ?, 'partner', '2026-01-01')
            """,
            (generate_password_hash("LegacyPass123!"),),
        )
        database.execute(
            """
            INSERT INTO attendance (user_id, attendance_date, check_in, completed_count)
            VALUES (2, ?, '2026-01-01T09:00:00+05:30', 3)
            """,
            (date.today().isoformat(),),
        )
        database.commit()
        database.close()

        migrated_app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "migration-test-secret",
                "DATABASE": str(database_path),
                "ADMIN_USERNAME": "admin",
                "ADMIN_EMAIL": "admin@example.com",
                "ADMIN_PASSWORD": "TestAdmin123!",
            }
        )
        client = migrated_app.test_client()
        csrf = client.get("/api/auth/csrf").get_json()["csrf_token"]
        login = client.post(
            "/api/auth/login",
            json={"email": "legacy_rider", "password": "LegacyPass123!"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(login.status_code, 200)
        self.assertIsNone(login.get_json()["user"]["email"])
        self.assertEqual(client.get("/api/dashboard").get_json()["lifetime_earnings"], 45)

        migrated_database = sqlite3.connect(database_path)
        try:
            admin_email = migrated_database.execute(
                "SELECT email FROM users WHERE username = 'admin'"
            ).fetchone()[0]
        finally:
            migrated_database.close()
        self.assertEqual(admin_email, "admin@example.com")


if __name__ == "__main__":
    unittest.main()
