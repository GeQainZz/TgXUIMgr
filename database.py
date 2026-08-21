import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DB_DIR = os.environ.get("DB_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
DB_PATH = os.path.join(DB_DIR, "traffic.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS traffic_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_name  TEXT    NOT NULL,
            email       TEXT    NOT NULL,
            record_date TEXT    NOT NULL,
            upload      INTEGER DEFAULT 0,
            download    INTEGER DEFAULT 0,
            total_bytes INTEGER DEFAULT 0,
            expiry_time INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now','localtime')),
            UNIQUE(panel_name, email, record_date)
        );
        CREATE INDEX IF NOT EXISTS idx_tr_date  ON traffic_records(record_date);
        CREATE INDEX IF NOT EXISTS idx_tr_panel ON traffic_records(panel_name);
        CREATE INDEX IF NOT EXISTS idx_tr_email ON traffic_records(email);
        CREATE TABLE IF NOT EXISTS query_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT    NOT NULL,
            actor       TEXT    NOT NULL,
            panel_name  TEXT    NOT NULL,
            email       TEXT    NOT NULL,
            success     INTEGER DEFAULT 0,
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_ql_created ON query_logs(created_at);
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialised at %s", DB_PATH)


def batch_record_traffic(records: List[Tuple]):
    """Each tuple: (panel_name, email, upload, download, total_bytes, expiry_time, record_date)"""
    if not records:
        return
    conn = _get_conn()
    conn.executemany(
       """INSERT INTO traffic_records
               (panel_name, email, upload, download, total_bytes, expiry_time, record_date)
          VALUES (?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(panel_name, email, record_date)
           DO UPDATE SET upload=excluded.upload, download=excluded.download,
                         total_bytes=excluded.total_bytes, expiry_time=excluded.expiry_time,
                         created_at=datetime('now','localtime')""",
        records,
    )
    conn.commit()
    conn.close()


def cleanup_old_traffic(retention_days: int = 365,
                        reference_date: Optional[str] = None) -> int:
    """Delete snapshots outside the inclusive retention window."""
    retention_days = max(1, int(retention_days))
    if reference_date:
        reference = datetime.strptime(reference_date, "%Y-%m-%d").date()
    else:
        reference = datetime.now().date()
    cutoff = reference - timedelta(days=retention_days - 1)

    conn = _get_conn()
    cursor = conn.execute(
        "DELETE FROM traffic_records WHERE record_date < ?",
        (cutoff.strftime("%Y-%m-%d"),),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info("Removed %s traffic records older than %s.", deleted, cutoff)
    return deleted


def _delta_cte() -> str:
    """Reusable CTE: computes per-row daily deltas from consecutive cumulative snapshots."""
    return """
    WITH deltas AS (
        SELECT
            a.record_date,
            a.panel_name,
            a.email,
            CASE
                WHEN b.upload   IS NOT NULL AND a.upload   >= b.upload
                    THEN a.upload   - b.upload
               WHEN b.upload   IS NOT NULL AND a.upload   <  b.upload
                   THEN a.upload
                ELSE 0
           END AS delta_up,
           CASE
               WHEN b.download IS NOT NULL AND a.download >= b.download
                   THEN a.download - b.download
               WHEN b.download IS NOT NULL AND a.download <  b.download
                   THEN a.download
                ELSE 0
           END AS delta_down
        FROM traffic_records a
        LEFT JOIN traffic_records b
            ON b.panel_name  = a.panel_name
           AND b.email       = a.email
           AND b.record_date = date(a.record_date, '-1 day')
    )
    """


def get_daily_stats(start_date: str, end_date: str,
                    panel_name: Optional[str] = None) -> List[Dict]:
    conn = _get_conn()
    where = ["deltas.record_date >= ?", "deltas.record_date <= ?"]
    params: list = [start_date, end_date]
    if panel_name:
        where.append("deltas.panel_name = ?")
        params.append(panel_name)
    sql = _delta_cte() + f"""
        SELECT record_date,
               SUM(delta_up) AS total_upload,
               SUM(delta_down) AS total_download,
               SUM(delta_up + delta_down) AS daily_total
        FROM deltas
        WHERE {' AND '.join(where)}
        GROUP BY record_date
        ORDER BY record_date
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{"record_date": r["record_date"],
             "total_upload": r["total_upload"] or 0,
             "total_download": r["total_download"] or 0,
             "daily_total": r["daily_total"] or 0} for r in rows]


def get_panel_daily_stats(start_date: str, end_date: str) -> List[Dict]:
    conn = _get_conn()
    sql = _delta_cte() + """
        SELECT record_date, panel_name,
               SUM(delta_up + delta_down) AS daily_total
        FROM deltas
        WHERE record_date >= ? AND record_date <= ?
        GROUP BY record_date, panel_name
        ORDER BY record_date, panel_name
    """
    rows = conn.execute(sql, [start_date, end_date]).fetchall()
    conn.close()
    return [{"record_date": r["record_date"],
             "panel_name": r["panel_name"],
             "daily_total": r["daily_total"] or 0} for r in rows]


def get_user_daily_stats(start_date: str, end_date: str,
                          panel_name: str, email: Optional[str] = None,
                          limit: int = 100) -> List[Dict]:
    conn = _get_conn()
    params: list = [start_date, end_date, panel_name]
    where = ["deltas.record_date >= ?", "deltas.record_date <= ?", "deltas.panel_name = ?"]
    if email:
        where.append("deltas.email = ?")
        params.append(email)
    sql = _delta_cte() + f"""
        SELECT record_date, email,
               SUM(delta_up + delta_down) AS daily_total
        FROM deltas
        WHERE {' AND '.join(where)}
        GROUP BY record_date, email
        ORDER BY record_date, daily_total DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{"record_date": r["record_date"],
             "email": r["email"],
             "daily_total": r["daily_total"] or 0} for r in rows]


def get_top_users(start_date: str, end_date: str,
                  panel_name: Optional[str] = None, limit: int = 20) -> List[Dict]:
    conn = _get_conn()
    where = ["deltas.record_date >= ?", "deltas.record_date <= ?"]
    params: list = [start_date, end_date]
    if panel_name:
        where.append("deltas.panel_name = ?")
        params.append(panel_name)
    sql = _delta_cte() + f"""
        SELECT email, panel_name,
               SUM(delta_up + delta_down) AS total_usage
        FROM deltas
        WHERE {' AND '.join(where)}
        GROUP BY email, panel_name
        ORDER BY total_usage DESC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [{"email": r["email"],
             "panel_name": r["panel_name"],
             "total_usage": r["total_usage"] or 0} for r in rows]


def get_latest_snapshot(panel_name: Optional[str] = None) -> List[Dict]:
    conn = _get_conn()
    if panel_name:
        sql = """
            SELECT t.* FROM traffic_records t
            INNER JOIN (
                SELECT panel_name, email, MAX(record_date) AS maxd
                FROM traffic_records GROUP BY panel_name, email
            ) m ON t.panel_name = m.panel_name
               AND t.email = m.email
               AND t.record_date = m.maxd
            WHERE t.panel_name = ?
            ORDER BY (t.upload + t.download) DESC
        """
        rows = conn.execute(sql, (panel_name,)).fetchall()
    else:
        sql = """
            SELECT t.* FROM traffic_records t
            INNER JOIN (
                SELECT panel_name, email, MAX(record_date) AS maxd
                FROM traffic_records GROUP BY panel_name, email
            ) m ON t.panel_name = m.panel_name
               AND t.email = m.email
               AND t.record_date = m.maxd
            ORDER BY t.panel_name, (t.upload + t.download) DESC
        """
        rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_date_range() -> Optional[Tuple[str, str]]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT MIN(record_date) AS mind, MAX(record_date) AS maxd FROM traffic_records"
    ).fetchone()
    conn.close()
    if row and row["mind"]:
        return row["mind"], row["maxd"]
    return None


def has_daily_traffic_snapshot(record_date: str) -> bool:
    """Return whether a date has the scheduled end-of-day traffic snapshot."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT 1 FROM traffic_records
           WHERE record_date = ? AND time(created_at) >= '23:00:00'
           LIMIT 1""",
        (record_date,),
    ).fetchone()
    conn.close()
    return row is not None


def record_query_log(source: str, actor: str, panel_name: str, email: str, success: bool) -> None:
    """Persist a single query log entry (TG bot or Web)."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO query_logs (source, actor, panel_name, email, success)
           VALUES (?, ?, ?, ?, ?)""",
        (source, str(actor), panel_name or "", email or "", 1 if success else 0),
    )
    conn.commit()
    conn.close()


def get_query_logs(limit: int = 200) -> List[Dict]:
    """Return recent query log entries newest-first."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT id, source, actor, panel_name, email, success, created_at
           FROM query_logs
           ORDER BY id DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_panel_user_list(panel_name: str) -> List[str]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT email FROM traffic_records WHERE panel_name = ? ORDER BY email",
        (panel_name,),
    ).fetchall()
    conn.close()
    return [r["email"] for r in rows]


def get_panel_summary_for_date(panel_name: str, record_date: str) -> List[Dict]:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM traffic_records
           WHERE panel_name = ? AND record_date = ?
           ORDER BY (upload + download) DESC""",
        (panel_name, record_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
