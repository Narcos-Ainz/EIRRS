import argparse
import csv
import hashlib
import json
import logging
import mimetypes
import os
import sqlite3
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[
        logging.FileHandler("logs/eirrs.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EIRRS-CORE")
DB_FILE = "emergency_system.db"

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def init_db() -> None:
    logger.info("Initializing database schema...")
    with get_db_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                role TEXT DEFAULT 'citizen',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                location_address TEXT NOT NULL,
                status TEXT DEFAULT 'reported',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER NOT NULL,
                responder_id INTEGER,
                status_update TEXT NOT NULL,
                notes TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        admin_pwd_hash = hash_password("admin123")
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, full_name, email, password_hash, phone_number, role)
            VALUES (1, 'Bojuwoye Edeosa', 'admin@eirrs.gov.ng', ?, '+2348001234567', 'admin')
            """,
            (admin_pwd_hash,)
        )
        conn.commit()
    logger.info("Database initialized. Default Admin: admin@eirrs.gov.ng / admin123")

def seed_sample_incidents() -> None:
    sample_records = [
        (1, 'fire', 'Transformer Fire', 'Active flames on power grid unit near residential block.', 'HIGH', 6.5244, 3.3792, 'Yaba, Lagos', 'reported'),
        (1, 'accident', 'Multi-car Expressway Collision', 'Three vehicles involved with multiple injuries.', 'CRITICAL', 6.6018, 3.3515, 'Ikeja, Lagos', 'reported'),
        (1, 'flooding', 'Canal Overflow Drainage Failure', 'Heavy stormwater blockage affecting major road commuters.', 'MEDIUM', 6.4531, 3.4245, 'Victoria Island, Lagos', 'reported')
    ]
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO incidents (user_id, category, title, description, severity, latitude, longitude, location_address, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sample_records
        )
        conn.commit()
    logger.info("Sample incidents seeded.")

def classify_severity(description: str) -> str:
    keywords = {
        "CRITICAL": ["explosion", "dead", "fatal", "trapped", "collapse", "gunfire", "cardiac"],
        "HIGH": ["flames", "fire", "heavy flooding", "bleeding", "unconscious", "injury"],
        "MEDIUM": ["smoke", "minor injury", "fender bender", "blocked road", "water leak"],
        "LOW": ["pothole", "streetlight", "noise", "graffiti", "trash"]
    }
    desc_lower = description.lower()
    for sev, words in keywords.items():
        if any(w in desc_lower for w in words):
            return sev
    return "MEDIUM"

def generate_matplotlib_charts() -> str:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT category, COUNT(*) as cnt FROM incidents GROUP BY category")
        cat_data = cur.fetchall()
        cur.execute("SELECT severity, COUNT(*) as cnt FROM incidents GROUP BY severity")
        sev_data = cur.fetchall()

    categories = [r["category"].capitalize() for r in cat_data] or ["None"]
    cat_counts = [r["cnt"] for r in cat_data] or [0]
    severities = [r["severity"] for r in sev_data] or ["None"]
    sev_counts = [r["cnt"] for r in sev_data] or [0]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
    ax1.bar(categories, cat_counts, color="#0284c7")
    ax1.set_title("Incidents by Category")

    colors = {"LOW": "#16a34a", "MEDIUM": "#b45309", "HIGH": "#e67e22", "CRITICAL": "#d92635"}
    pie_colors = [colors.get(s, "#0284c7") for s in severities]
    ax2.pie(sev_counts, labels=severities, autopct="%1.1f%%", colors=pie_colors, startangle=140)
    ax2.set_title("Severity Distribution")

    chart_path = "reports/analytics_summary.png"
    plt.tight_layout()
    plt.savefig(chart_path, dpi=200)
    plt.close()
    return chart_path

class EIRRSRequestHandler(BaseHTTPRequestHandler):

    def _send_json(self, status_code: int, data: Dict[str, Any]):
        try:
            response_bytes = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.end_headers()
            self.wfile.write(response_bytes)
        except Exception as e:
            logger.error(f"Error sending JSON response: {str(e)}")

    def _send_file(self, filepath: str, content_type: Optional[str] = None):
        if not os.path.exists(filepath):
            self.send_error(404, f"File Not Found: {filepath}")
            return
        if not content_type:
            content_type, _ = mimetypes.guess_type(filepath)
            content_type = content_type or "application/octet-stream"

        with open(filepath, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _parse_json_body(self) -> Dict[str, Any]:
        try:
            content_length_header = self.headers.get("Content-Length")
            if not content_length_header:
                return {}
            content_len = int(content_length_header)
            if content_len == 0:
                return {}
            raw = self.rfile.read(content_len).decode("utf-8").strip()
            return json.loads(raw) if raw else {}
        except Exception as e:
            logger.error(f"JSON Parse Exception: {str(e)}")
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/")
            query_params = urllib.parse.parse_qs(parsed.query)


            # API 2: Incidents List with Filters
            if path == "/api/incidents":
                category = query_params.get("category", [None])[0]
                severity = query_params.get("severity", [None])[0]
                status = query_params.get("status", [None])[0]
                user_id = query_params.get("user_id", [None])[0]
                search = query_params.get("search", [None])[0]

                sql = "SELECT * FROM incidents WHERE 1=1"
                params: List[Any] = []

                if category and category != "all":
                    sql += " AND category = ?"
                    params.append(category)
                if severity and severity != "all":
                    sql += " AND severity = ?"
                    params.append(severity)
                if status and status != "all":
                    sql += " AND status = ?"
                    params.append(status)
                if user_id:
                    sql += " AND user_id = ?"
                    params.append(int(user_id))
                if search:
                    sql += " AND (title LIKE ? OR description LIKE ? OR location_address LIKE ?)"
                    term = f"%{search}%"
                    params.extend([term, term, term])

                sql += " ORDER BY created_at DESC"
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(sql, params)
                    rows = [dict(row) for row in cur.fetchall()]
                return self._send_json(200, {"success": True, "count": len(rows), "data": rows})

            # API 3: Single Incident + Response Logs
            if path.startswith("/api/incidents/") and len(path.split("/")) == 4:
                inc_id = int(path.split("/")[-1])
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM incidents WHERE id = ?", (inc_id,))
                    row = cur.fetchone()
                    if not row:
                        return self._send_json(404, {"success": False, "error": "Not Found"})
                    cur.execute("SELECT * FROM responses WHERE incident_id = ? ORDER BY timestamp DESC", (inc_id,))
                    data = dict(row)
                    data["responses"] = [dict(r) for r in cur.fetchall()]
                return self._send_json(200, {"success": True, "data": data})

            # API 4: Analytics Chart
            if path == "/api/reports/chart":
                chart_file = generate_matplotlib_charts()
                return self._send_file(chart_file, "image/png")

            # API 5: CSV Export
            if path == "/api/reports/export/csv":
                csv_path = "reports/incidents_export.csv"
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM incidents ORDER BY created_at DESC")
                    rows = cur.fetchall()
                if rows:
                    with open(csv_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(rows[0].keys())
                        for r in rows:
                            writer.writerow(list(r))
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header("Content-Disposition", 'attachment; filename="incident_reports.csv"')
                with open(csv_path, "rb") as f:
                    csv_data = f.read()
                self.send_header("Content-Length", str(len(csv_data)))
                self.end_headers()
                self.wfile.write(csv_data)
                return

            # Prevent unhandled API paths from serving HTML
            if path.startswith("/api"):
                return self._send_json(404, {"success": False, "error": f"API Route Not Found: {path}"})

            # Static Files
            if path.startswith("/static"):
                return self._send_file(path.lstrip("/"))

            # Template Resolution
            page = path.lstrip("/")
            if page == "" or page == "index.html":
                target = "templates/index.html"
            else:
                target = f"templates/{page}"

            if not target.endswith(".html") and not os.path.exists(target):
                target += ".html"

            if os.path.exists(target):
                return self._send_file(target, "text/html")
            return self.send_error(404, f"Page Not Found: {target}")

        except Exception as e:
            logger.error(f"GET Routing Error on {self.path}: {str(e)}")
            self._send_json(500, {"success": False, "error": f"Server Error: {str(e)}"})

    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/")
            payload = self._parse_json_body()

            # Authentication: Login
            if path == "/api/auth/login":
                email = payload.get("email", "").strip().lower()
                password = payload.get("password", "").strip()

                if not email or not password:
                    return self._send_json(400, {"success": False, "error": "Email and password are required."})

                pwd_hash = hash_password(password)
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT id, full_name, email, phone_number, role FROM users WHERE LOWER(email) = ? AND password_hash = ?",
                        (email, pwd_hash)
                    )
                    user = cur.fetchone()
                    if not user:
                        return self._send_json(401, {"success": False, "error": "Invalid email or password."})

                return self._send_json(200, {"success": True, "message": "Login successful", "user": dict(user)})

            # Authentication: Register
            if path == "/api/auth/register":
                full_name = payload.get("full_name", "").strip()
                email = payload.get("email", "").strip().lower()
                phone = payload.get("phone_number", "").strip()
                password = payload.get("password", "")

                if not full_name or not email or not password:
                    return self._send_json(400, {"success": False, "error": "All fields are required."})

                pwd_hash = hash_password(password)
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
                    if cur.fetchone():
                        return self._send_json(409, {"success": False, "error": "Email is already registered."})

                    cur.execute(
                        "INSERT INTO users (full_name, email, password_hash, phone_number, role) VALUES (?, ?, ?, ?, ?)",
                        (full_name, email, pwd_hash, phone, 'citizen')
                    )
                    user_id = cur.lastrowid
                    conn.commit()

                return self._send_json(201, {"success": True, "user_id": user_id})

            # Submit Incident
            if path == "/api/incidents":
                title = payload.get("title", "").strip()
                description = payload.get("description", "").strip()
                if not title or not description:
                    return self._send_json(400, {"success": False, "error": "Title and description required."})

                severity = payload.get("severity") or classify_severity(description)
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO incidents (user_id, category, title, description, severity, latitude, longitude, location_address)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            payload.get("user_id", 1),
                            payload.get("category", "other"),
                            title,
                            description,
                            severity,
                            float(payload.get("latitude", 6.5244)),
                            float(payload.get("longitude", 3.3792)),
                            payload.get("location_address", "Lagos, Nigeria").strip()
                        )
                    )
                    incident_id = cur.lastrowid
                    conn.commit()
                return self._send_json(201, {"success": True, "incident_id": incident_id, "inferred_severity": severity})

            return self._send_json(404, {"success": False, "error": f"API Endpoint Not Found: {path}"})

        except Exception as e:
            logger.error(f"POST Routing Error on {self.path}: {str(e)}")
            self._send_json(500, {"success": False, "error": f"Server Error: {str(e)}"})

    def do_PUT(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path.rstrip("/")
            payload = self._parse_json_body()

            # Profile Updates
            if path.startswith("/api/users"):
                user_id = int(path.split("/")[-1])
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE users SET full_name = ?, phone_number = ? WHERE id = ?",
                        (payload.get("full_name", "").strip(), payload.get("phone_number", "").strip(), user_id)
                    )
                    conn.commit()
                return self._send_json(200, {"success": True})

            # Incident Verification & Status Transitions
            if path.startswith("/api/incidents"):
                inc_id = int(path.split("/")[-1])
                status = payload.get("status")
                notes = payload.get("notes", "Status updated by command personnel.")
                responder_id = payload.get("responder_id", 1)

                if not status:
                    return self._send_json(400, {"success": False, "error": "Status is required."})

                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("UPDATE incidents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, inc_id))
                    cur.execute(
                        "INSERT INTO responses (incident_id, responder_id, status_update, notes) VALUES (?, ?, ?, ?)",
                        (inc_id, responder_id, status, notes)
                    )
                    conn.commit()
                return self._send_json(200, {"success": True, "message": f"Incident #{inc_id} updated to {status}."})

            return self._send_json(404, {"success": False, "error": f"API Endpoint Not Found: {path}"})

        except Exception as e:
            logger.error(f"PUT Routing Error on {self.path}: {str(e)}")
            self._send_json(500, {"success": False, "error": f"Server Error: {str(e)}"})

def main():
    parser = argparse.ArgumentParser(description="Emergency Incident Reporting & Response System (EIRRS)")
    parser.add_argument("--init-db", action="store_true", help="Initialize the database.")
    parser.add_argument("--seed", action="store_true", help="Seed default emergency incidents.")
    parser.add_argument("--run-server", action="store_true", help="Run HTTP server.")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind (default: 5000).")
    args = parser.parse_args()

    if args.init_db:
        init_db()

    if args.seed:
        seed_sample_incidents()

    if args.run_server or (not args.init_db and not args.seed):
        init_db()
        server_address = ("", args.port)
        httpd = HTTPServer(server_address, EIRRSRequestHandler)
        logger.info(f"EIRRS Server running securely at http://localhost:{args.port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Graceful shutdown.")
            httpd.server_close()

if __name__ == "__main__":
    main()