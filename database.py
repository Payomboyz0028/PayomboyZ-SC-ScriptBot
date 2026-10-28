# -*- coding: utf-8 -*-
"""
PAYOMBØYZ Dispatch Database Engine
Industrial SQLite database with WAL mode, Concurrency Mutex Locks, and Transaction Safety.
"""

from __future__ import annotations
import sqlite3
import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

from config import DB_PATH, DEFAULT_STAFF_ROLE_ID, DEFAULT_OWNER_ROLE_ID, DEFAULT_CATEGORY_ID


class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        # WAL mode enables high concurrency between background writers and readers
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id TEXT PRIMARY KEY,
                verified_role_id INTEGER,
                owner_role_id INTEGER,
                staff_role_id INTEGER,
                category_id INTEGER,
                transcript_log_channel_id INTEGER,
                web_api_url TEXT,
                web_api_token TEXT,
                slip_api_url TEXT,
                slip_api_key TEXT,
                counter INTEGER DEFAULT 0,
                dept_roles_json TEXT
            );

            CREATE TABLE IF NOT EXISTS pending_calls (
                call_id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                category_key TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                status TEXT DEFAULT 'waiting', -- 'waiting', 'claimed', 'cancelled'
                claimed_by INTEGER,
                created_at REAL NOT NULL,
                claimed_at REAL
            );

            CREATE TABLE IF NOT EXISTS active_tickets (
                channel_id INTEGER PRIMARY KEY,
                ticket_num INTEGER NOT NULL,
                guild_id TEXT NOT NULL,
                category_key TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                claimed_admin_id INTEGER NOT NULL,
                process_stage TEXT DEFAULT 'queued', -- 'queued', 'started', 'in_progress', 'final_stage', 'completed'
                paid_status INTEGER DEFAULT 0,
                slip_ref TEXT,
                amount REAL DEFAULT 0.0,
                created_at REAL NOT NULL,
                ongoing_msg_id INTEGER DEFAULT 0,
                ongoing_ch_id INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS slip_ledger (
                slip_ref TEXT PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                verified_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS captcha_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ticket_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                ticket_num INTEGER,
                guild_id TEXT NOT NULL,
                category_key TEXT NOT NULL,
                customer_id INTEGER NOT NULL,
                claimed_admin_id INTEGER NOT NULL,
                paid_status INTEGER DEFAULT 0,
                amount REAL DEFAULT 0.0,
                slip_ref TEXT,
                created_at REAL NOT NULL,
                closed_at REAL NOT NULL,
                close_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS daily_audit_stats (
                date_str TEXT PRIMARY KEY,
                joins_count INTEGER DEFAULT 0,
                leaves_count INTEGER DEFAULT 0,
                verified_count INTEGER DEFAULT 0
            );
            """)
            # Safe schema migrations for existing database files
            try:
                conn.execute("ALTER TABLE active_tickets ADD COLUMN ongoing_msg_id INTEGER DEFAULT 0;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE active_tickets ADD COLUMN ongoing_ch_id INTEGER DEFAULT 0;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE guild_configs ADD COLUMN truemoney_phone TEXT DEFAULT '';")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE guild_configs ADD COLUMN verified_slip_channel_id INTEGER DEFAULT 1563251864256909444;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE guild_configs ADD COLUMN role_audit_channel_id INTEGER DEFAULT 1563251907567419532;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE guild_configs ADD COLUMN welcome_channel_id INTEGER DEFAULT 1563251676830236782;")
            except Exception:
                pass
            conn.commit()

    # ─────────────────────────────────────────────────────────────
    # Guild Configuration
    # ─────────────────────────────────────────────────────────────
    def get_guild_config(self, guild_id: int | str) -> Dict[str, Any]:
        gid = str(guild_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM guild_configs WHERE guild_id = ?", (gid,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                if d.get("dept_roles_json"):
                    try:
                        d["dept_roles"] = json.loads(d["dept_roles_json"])
                    except Exception:
                        d["dept_roles"] = {}
                else:
                    d["dept_roles"] = {}
                return d
            
            # Default configuration insertion
            default_cfg = {
                "guild_id": gid,
                "verified_role_id": None,
                "owner_role_id": DEFAULT_OWNER_ROLE_ID,
                "staff_role_id": DEFAULT_STAFF_ROLE_ID,
                "category_id": DEFAULT_CATEGORY_ID,
                "transcript_log_channel_id": None,
                "web_api_url": None,
                "web_api_token": None,
                "slip_api_url": None,
                "slip_api_key": None,
                "truemoney_phone": "",
                "verified_slip_channel_id": 1563251864256909444,
                "role_audit_channel_id": 1563251907567419532,
                "counter": 0,
                "dept_roles_json": "{}"
            }
            cursor.execute("""
                INSERT INTO guild_configs (
                    guild_id, verified_role_id, owner_role_id, staff_role_id, 
                    category_id, transcript_log_channel_id, counter, dept_roles_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                gid, default_cfg["verified_role_id"], default_cfg["owner_role_id"],
                default_cfg["staff_role_id"], default_cfg["category_id"],
                default_cfg["transcript_log_channel_id"], default_cfg["counter"],
                default_cfg["dept_roles_json"]
            ))
            conn.commit()
            default_cfg["dept_roles"] = {}
            return default_cfg

    def update_guild_config(self, guild_id: int | str, **kwargs):
        gid = str(guild_id)
        self.get_guild_config(gid)  # Ensure row exists
        
        allowed_cols = {
            "verified_role_id", "owner_role_id", "staff_role_id",
            "category_id", "transcript_log_channel_id", "web_api_url",
            "web_api_token", "slip_api_url", "slip_api_key", "counter",
            "dept_roles_json", "truemoney_phone", "verified_slip_channel_id",
            "role_audit_channel_id", "welcome_channel_id"
        }
        
        updates = []
        vals = []
        for k, v in kwargs.items():
            if k == "dept_roles":
                updates.append("dept_roles_json = ?")
                vals.append(json.dumps(v, ensure_ascii=False))
            elif k in allowed_cols:
                updates.append(f"{k} = ?")
                vals.append(v)
                
        if not updates:
            return

        vals.append(gid)
        with self._get_connection() as conn:
            conn.execute(f"UPDATE guild_configs SET {', '.join(updates)} WHERE guild_id = ?", vals)
            conn.commit()

    def get_next_counter(self, guild_id: int | str) -> int:
        gid = str(guild_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE guild_configs SET counter = counter + 1 WHERE guild_id = ?", (gid,))
            cursor.execute("SELECT counter FROM guild_configs WHERE guild_id = ?", (gid,))
            row = cursor.fetchone()
            conn.commit()
            return row["counter"] if row else 1

    # ─────────────────────────────────────────────────────────────
    # CAPTCHA Session Verification
    # ─────────────────────────────────────────────────────────────
    def create_captcha_session(self, user_id: int, code: str, ttl: int = 300) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        expires = now + ttl
        with self._get_connection() as conn:
            # Purge expired sessions for this user
            conn.execute("DELETE FROM captcha_sessions WHERE user_id = ? OR expires_at < ?", (user_id, now))
            conn.execute("""
                INSERT INTO captcha_sessions (session_id, user_id, code, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (session_id, user_id, code.upper(), now, expires))
            conn.commit()
        return session_id

    def verify_captcha(self, user_id: int, input_code: str) -> bool:
        now = time.time()
        clean_input = input_code.strip().replace(" ", "").upper()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT session_id, code FROM captcha_sessions 
                WHERE user_id = ? AND expires_at > ? 
                ORDER BY created_at DESC LIMIT 1
            """, (user_id, now))
            row = cursor.fetchone()
            if not row:
                return False
            
            is_valid = (row["code"] == clean_input)
            if is_valid:
                conn.execute("DELETE FROM captcha_sessions WHERE user_id = ?", (user_id,))
                conn.commit()
            return is_valid

    # ─────────────────────────────────────────────────────────────
    # Department Lobby & Single-Admin Mutex Lock
    # ─────────────────────────────────────────────────────────────
    def create_pending_call(
        self, guild_id: int | str, category_key: str, customer_id: int, 
        channel_id: int, message_id: int
    ) -> str:
        call_id = f"call_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO pending_calls (
                    call_id, guild_id, category_key, customer_id, channel_id, message_id, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?)
            """, (call_id, str(guild_id), category_key, customer_id, channel_id, message_id, now))
            conn.commit()
        return call_id

    def get_pending_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_calls WHERE call_id = ?", (call_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    async def claim_pending_call_atomic(self, call_id: str, admin_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        ATOMIC MUTEX LOCK:
        Attempts to update status from 'waiting' to 'claimed'.
        Returns (True, call_data) if this admin won the race.
        Returns (False, None) if another admin already claimed it.
        """
        async with self._lock:
            now = time.time()
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE pending_calls 
                    SET status = 'claimed', claimed_by = ?, claimed_at = ? 
                    WHERE call_id = ? AND status = 'waiting'
                """, (admin_id, now, call_id))
                
                if cursor.rowcount == 1:
                    conn.commit()
                    cursor.execute("SELECT * FROM pending_calls WHERE call_id = ?", (call_id,))
                    row = cursor.fetchone()
                    return True, dict(row) if row else None
                else:
                    conn.commit()
                    return False, None

    # ─────────────────────────────────────────────────────────────
    # Active Tickets & Dual-Track Process
    # ─────────────────────────────────────────────────────────────
    def register_ticket(
        self, channel_id: int, ticket_num: int, guild_id: int | str,
        category_key: str, customer_id: int, claimed_admin_id: int
    ):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO active_tickets (
                    channel_id, ticket_num, guild_id, category_key, 
                    customer_id, claimed_admin_id, process_stage, paid_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'queued', 0, ?)
            """, (channel_id, ticket_num, str(guild_id), category_key, customer_id, claimed_admin_id, now))
            conn.commit()

    def get_ticket(self, channel_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM active_tickets WHERE channel_id = ?", (channel_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def find_user_open_ticket(self, guild_id: int | str, customer_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM active_tickets 
                WHERE guild_id = ? AND customer_id = ?
            """, (str(guild_id), customer_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_ticket_stage(self, channel_id: int, stage: str):
        with self._get_connection() as conn:
            conn.execute("UPDATE active_tickets SET process_stage = ? WHERE channel_id = ?", (stage, channel_id))
            conn.commit()

    def update_ticket_payment(self, channel_id: int, slip_ref: str, amount: float, slip_image_path: str = ""):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE active_tickets 
                SET paid_status = 1, slip_ref = ?, amount = ?, slip_image_path = ? 
                WHERE channel_id = ?
            """, (slip_ref, amount, slip_image_path, channel_id))
            conn.commit()

    def update_ticket_amount(self, channel_id: int, amount: float):
        with self._get_connection() as conn:
            conn.execute("UPDATE active_tickets SET amount = ? WHERE channel_id = ?", (amount, channel_id))
            conn.commit()

    def set_ticket_ongoing_message(self, channel_id: int, ongoing_msg_id: int, ongoing_ch_id: int):
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE active_tickets 
                SET ongoing_msg_id = ?, ongoing_ch_id = ? 
                WHERE channel_id = ?
            """, (ongoing_msg_id, ongoing_ch_id, channel_id))
            conn.commit()

    def get_ticket_by_ongoing_message(self, ongoing_msg_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM active_tickets WHERE ongoing_msg_id = ?", (ongoing_msg_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_active_tickets_by_category(self, guild_id: int | str, category_key: Optional[str] = None) -> list[Dict[str, Any]]:
        gid = str(guild_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category_key:
                cursor.execute("""
                    SELECT * FROM active_tickets 
                    WHERE (guild_id = ? OR guild_id = '') AND category_key = ?
                    ORDER BY ticket_num ASC
                """, (gid, category_key))
            else:
                cursor.execute("""
                    SELECT * FROM active_tickets 
                    WHERE (guild_id = ? OR guild_id = '')
                    ORDER BY ticket_num ASC
                """, (gid,))
            return [dict(r) for r in cursor.fetchall()]

    def close_ticket(self, channel_id: int):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM active_tickets WHERE channel_id = ?", (channel_id,))
            conn.commit()

    # ─────────────────────────────────────────────────────────────
    # Anti-Replay Slip Ledger
    # ─────────────────────────────────────────────────────────────
    def check_and_record_slip(self, slip_ref: str, channel_id: int, customer_id: int, amount: float) -> bool:
        """
        Anti-Replay Ledger:
        Returns True if the slip is completely new and recorded.
        Returns False if the slip has already been recorded in the past.
        """
        clean_ref = slip_ref.strip()
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT slip_ref FROM slip_ledger WHERE slip_ref = ?", (clean_ref,))
            if cursor.fetchone():
                return False  # Duplicate slip detected!
            
            cursor.execute("""
                INSERT INTO slip_ledger (slip_ref, channel_id, customer_id, amount, verified_at)
                VALUES (?, ?, ?, ?, ?)
            """, (clean_ref, channel_id, customer_id, amount, now))
            conn.commit()
            return True

    # ─────────────────────────────────────────────────────────────
    # Ticket Archive History & Daily Stats
    # ─────────────────────────────────────────────────────────────
    def record_ticket_history(self, tdata: Dict[str, Any], close_reason: str = "ปิดปกติ"):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO ticket_history (
                    channel_id, ticket_num, guild_id, category_key, customer_id,
                    claimed_admin_id, paid_status, amount, slip_ref, slip_image_path, created_at, closed_at, close_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tdata.get("channel_id", 0),
                tdata.get("ticket_num", 0),
                str(tdata.get("guild_id", "")),
                tdata.get("category_key", "general"),
                tdata.get("customer_id", 0),
                tdata.get("claimed_admin_id", 0),
                tdata.get("paid_status", 0),
                tdata.get("amount", 0.0),
                tdata.get("slip_ref", ""),
                tdata.get("slip_image_path", ""),
                tdata.get("created_at", now),
                now,
                close_reason
            ))

            # Automatically partition slip to claimed admin for Website Back-Office
            if tdata.get("amount", 0.0) > 0 or tdata.get("slip_ref"):
                s_ref = tdata.get("slip_ref") or f"TICKET_{tdata.get('ticket_num', 0)}_{int(now)}"
                try:
                    conn.execute("""
                        INSERT INTO admin_slip_partitions (
                            slip_ref, ticket_num, channel_id, claimed_admin_id, customer_id,
                            amount, category_key, slip_image_path, verified_at, closed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(slip_ref) DO UPDATE SET
                            closed_at = excluded.closed_at,
                            claimed_admin_id = excluded.claimed_admin_id,
                            slip_image_path = CASE WHEN excluded.slip_image_path != '' THEN excluded.slip_image_path ELSE admin_slip_partitions.slip_image_path END
                    """, (
                        s_ref,
                        tdata.get("ticket_num", 0),
                        tdata.get("channel_id", 0),
                        tdata.get("claimed_admin_id", 0),
                        tdata.get("customer_id", 0),
                        tdata.get("amount", 0.0),
                        tdata.get("category_key", "general"),
                        tdata.get("slip_image_path", ""),
                        tdata.get("created_at", now),
                        now
                    ))
                except Exception:
                    pass

            conn.commit()

    def increment_audit_stat(self, stat_type: str, date_str: Optional[str] = None):
        """Increments 'joins_count', 'leaves_count', or 'verified_count' for the given date (default today YYYY-MM-DD ICT)."""
        if not date_str:
            import datetime
            ict_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
            date_str = ict_now.strftime("%Y-%m-%d")

        allowed = {"joins_count", "leaves_count", "verified_count"}
        if stat_type not in allowed:
            return

        with self._get_connection() as conn:
            conn.execute(f"""
                INSERT INTO daily_audit_stats (date_str, {stat_type})
                VALUES (?, 1)
                ON CONFLICT(date_str) DO UPDATE SET {stat_type} = {stat_type} + 1
            """, (date_str,))
            conn.commit()

    def get_daily_summary_data(self, guild_id: int | str, start_ts: float, end_ts: float) -> Dict[str, Any]:
        """Aggregates revenue, ticket count, department split, and staff performance within [start_ts, end_ts]."""
        gid = str(guild_id)
        with self._get_connection() as conn:
            c = conn.cursor()

            # 1. Ticket history totals
            c.execute("""
                SELECT 
                    COUNT(*) as total_closed,
                    COALESCE(SUM(amount), 0.0) as total_revenue,
                    COALESCE(SUM(CASE WHEN paid_status = 1 THEN 1 ELSE 0 END), 0) as paid_orders
                FROM ticket_history
                WHERE (guild_id = ? OR guild_id = '') AND closed_at >= ? AND closed_at <= ?
            """, (gid, start_ts, end_ts))
            summary_row = c.fetchone()

            # Fallback if no ticket history closed today, check slip_ledger within time window
            c.execute("""
                SELECT COALESCE(SUM(amount), 0.0) as ledger_total, COUNT(*) as ledger_count
                FROM slip_ledger
                WHERE verified_at >= ? AND verified_at <= ?
            """, (start_ts, end_ts))
            slip_row = c.fetchone()

            total_revenue = max(summary_row["total_revenue"], slip_row["ledger_total"])

            # 2. Department Breakdown
            c.execute("""
                SELECT category_key, COUNT(*) as cnt, COALESCE(SUM(amount), 0.0) as rev
                FROM ticket_history
                WHERE (guild_id = ? OR guild_id = '') AND closed_at >= ? AND closed_at <= ?
                GROUP BY category_key
            """, (gid, start_ts, end_ts))
            dept_rows = c.fetchall()
            dept_breakdown = {r["category_key"]: {"count": r["cnt"], "revenue": r["rev"]} for r in dept_rows}

            # 3. Staff Leaderboard
            c.execute("""
                SELECT claimed_admin_id, COUNT(*) as cnt, COALESCE(SUM(amount), 0.0) as rev
                FROM ticket_history
                WHERE (guild_id = ? OR guild_id = '') AND closed_at >= ? AND closed_at <= ? AND claimed_admin_id > 0
                GROUP BY claimed_admin_id
                ORDER BY cnt DESC, rev DESC
                LIMIT 5
            """, (gid, start_ts, end_ts))
            staff_rows = c.fetchall()
            staff_leaderboard = [
                {"admin_id": r["claimed_admin_id"], "count": r["cnt"], "revenue": r["rev"]}
                for r in staff_rows
            ]

            # 4. Active Tickets snapshot
            c.execute("SELECT COUNT(*) as active_cnt FROM active_tickets WHERE guild_id = ?", (gid,))
            active_cnt = c.fetchone()["active_cnt"]

            # 5. Member Join/Leave/Verified stats
            import datetime
            ict_now = datetime.datetime.fromtimestamp(end_ts, tz=datetime.timezone(datetime.timedelta(hours=7)))
            date_str = ict_now.strftime("%Y-%m-%d")
            c.execute("SELECT * FROM daily_audit_stats WHERE date_str = ?", (date_str,))
            audit_row = c.fetchone()

            return {
                "date_str": date_str,
                "total_closed": summary_row["total_closed"],
                "total_revenue": total_revenue,
                "paid_orders": summary_row["paid_orders"],
                "active_tickets": active_cnt,
                "dept_breakdown": dept_breakdown,
                "staff_leaderboard": staff_leaderboard,
                "joins_count": audit_row["joins_count"] if audit_row else 0,
                "leaves_count": audit_row["leaves_count"] if audit_row else 0,
                "verified_count": audit_row["verified_count"] if audit_row else 0,
            }

    # ─────────────────────────────────────────────────────────────
    # Captcha Failure Counter (Brute Force Detection)
    # ─────────────────────────────────────────────────────────────
    _captcha_fails: Dict[int, int] = {}

    def record_captcha_failure(self, user_id: int) -> int:
        current = self._captcha_fails.get(user_id, 0) + 1
        self._captcha_fails[user_id] = current
        return current

    def reset_captcha_failure(self, user_id: int):
        self._captcha_fails.pop(user_id, None)


db = DatabaseManager()
