import sqlite3
from datetime import date, timedelta

DB_PATH = "checkout.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cameras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number INTEGER UNIQUE NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL REFERENCES cameras(id),
                student_name TEXT NOT NULL,
                netid TEXT NOT NULL,
                pickup_date TEXT NOT NULL,
                return_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'reserved',
                created_at TEXT NOT NULL DEFAULT (date('now')),
                CONSTRAINT valid_status CHECK (status IN ('reserved','checked_out','returned','cancelled'))
            );
        """)
        # Seed cameras 1-6 if none exist
        if conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO cameras (number) VALUES (?)",
                [(i,) for i in range(1, 7)]
            )


def get_cameras_with_status(target_date: str):
    """Return all active cameras with their status for a given date."""
    with get_db() as conn:
        cameras = conn.execute(
            "SELECT * FROM cameras WHERE active=1 ORDER BY number"
        ).fetchall()

        result = []
        for cam in cameras:
            res = conn.execute("""
                SELECT * FROM reservations
                WHERE camera_id=? AND status IN ('reserved','checked_out')
                AND pickup_date <= ? AND return_date >= ?
                ORDER BY CASE status WHEN 'checked_out' THEN 0 ELSE 1 END
                LIMIT 1
            """, (cam["id"], target_date, target_date)).fetchone()
            result.append({"camera": cam, "reservation": res})
        return result


def student_has_active(netid: str):
    """True if student has a reserved or checked-out reservation."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT id FROM reservations
            WHERE netid=? AND status IN ('reserved','checked_out')
            LIMIT 1
        """, (netid,)).fetchone()
        return row is not None


def camera_available(camera_id: int, pickup: str, return_d: str):
    """True if no active reservation overlaps the requested window."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT id FROM reservations
            WHERE camera_id=? AND status IN ('reserved','checked_out')
            AND pickup_date <= ? AND return_date >= ?
            LIMIT 1
        """, (camera_id, return_d, pickup)).fetchone()
        return row is None


def create_reservation(camera_id: int, name: str, netid: str, pickup: str):
    return_d = (date.fromisoformat(pickup) + timedelta(days=2)).isoformat()
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO reservations (camera_id, student_name, netid, pickup_date, return_date)
            VALUES (?, ?, ?, ?, ?)
        """, (camera_id, name, netid.lower().strip(), pickup, return_d))
        return cur.lastrowid


def cancel_reservation(reservation_id: int, netid: str = None):
    """Cancel by id. If netid provided, must match (student self-cancel)."""
    with get_db() as conn:
        if netid:
            conn.execute("""
                UPDATE reservations SET status='cancelled'
                WHERE id=? AND netid=? AND status='reserved'
            """, (reservation_id, netid))
        else:
            conn.execute("""
                UPDATE reservations SET status='cancelled' WHERE id=?
            """, (reservation_id,))


def set_status(reservation_id: int, status: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE reservations SET status=? WHERE id=?",
            (status, reservation_id)
        )


def extend_reservation(reservation_id: int, new_return: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE reservations SET return_date=? WHERE id=?",
            (new_return, reservation_id)
        )


def get_reservation_by_netid(netid: str):
    with get_db() as conn:
        return conn.execute("""
            SELECT r.*, c.number AS camera_number
            FROM reservations r JOIN cameras c ON c.id=r.camera_id
            WHERE r.netid=? AND r.status IN ('reserved','checked_out')
            ORDER BY r.pickup_date
            LIMIT 1
        """, (netid.lower().strip(),)).fetchone()


def get_all_reservations():
    with get_db() as conn:
        return conn.execute("""
            SELECT r.*, c.number AS camera_number
            FROM reservations r JOIN cameras c ON c.id=r.camera_id
            ORDER BY
                CASE r.status
                    WHEN 'checked_out' THEN 0
                    WHEN 'reserved' THEN 1
                    WHEN 'returned' THEN 2
                    ELSE 3
                END,
                r.return_date
        """).fetchall()


def add_camera():
    with get_db() as conn:
        max_num = conn.execute("SELECT MAX(number) FROM cameras").fetchone()[0] or 0
        conn.execute("INSERT INTO cameras (number) VALUES (?)", (max_num + 1,))
        return max_num + 1


def get_camera_by_id(camera_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM cameras WHERE id=?", (camera_id,)).fetchone()
