#!/usr/bin/env python3
"""
XController Telegram Admin Bot (Secure Enhanced Edition)

Features (approved set):
- Activation gate (admin DM 'activate')
- Single allowed group enforcement (ALLOWED_GROUP_ID)
- Uniform moderation for normal, forwarded and edited messages
- Immediate deletion of messages containing banned words
- Progressive penalties (delete + 12h mute -> permanent ban within 7d window)
- Username requirement on join (kick if missing) after activation
- Admin-only DM control (/orwell multi-add, /status, activate)
- Multi-add banned words: /orwell word1,word2,word3
- Daily rotating keyed BLAKE2b hashing salt (if SALT env missing) persisted & auto-rotated
- Encrypted SQLite (SQLCipher) storage (violations, banned_words, activation, dm_spam, salt_state)
- DM spam suppression: non-admin DM > threshold (50 default in 7d) → silent group ban + block
- Status summary without exposing hashed identities
- Substring + word-boundary banned-word detection (substring kept ON, documented)

Security design:
- If SALT provided: fixed mode (no rotation)
- If SALT not provided: secure random 32-byte hex salt rotated every 24h (violations & dm_spam reset)
- Keyed BLAKE2b (digest_size=32) for user_id anonymization
- SQLCipher encryption with passphrase DB_PASSPHRASE
"""

import os
import re
import logging
import asyncio
import time
import secrets
import sqlite3  # Will be overridden by pysqlcipher3 import below
from typing import Set, List, Tuple, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path

# SQLCipher driver
try:
    import pysqlcipher3.dbapi2 as sqlcipher
except ImportError as e:
    raise ImportError(
        "pysqlcipher3 is required. Install system dependencies (e.g. apt install sqlcipher libsqlcipher-dev) "
        "then pip install pysqlcipher3."
    ) from e

from telethon import TelegramClient, events, functions
from telethon.tl.types import ChatBannedRights
from telethon.errors import (
    ChatAdminRequiredError,
    UserAdminInvalidError,
    FloodWaitError
)
from dotenv import load_dotenv
from hashlib import blake2b

# Auto-generate secure environment variables if missing or invalid
try:
    from env_generator import ensure_secure_environment
    ensure_secure_environment()
except ImportError:
    # env_generator not available, skip auto-generation
    pass

load_dotenv()

# -----------------------------
# Data directory
# -----------------------------
def get_data_dir() -> Path:
    data_dir = Path("/data")
    if data_dir.exists() and data_dir.is_dir():
        try:
            tmp = data_dir / ".write_test"
            tmp.touch()
            tmp.unlink()
            return data_dir
        except (PermissionError, OSError):
            pass
    fallback = Path("./data")
    fallback.mkdir(exist_ok=True)
    return fallback

DATA_DIR = get_data_dir()

# -----------------------------
# Logging
# -----------------------------
log_file = DATA_DIR / "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("xcontroller")
logger.info(f"Using data directory: {DATA_DIR}")

# -----------------------------
# Rate limiting (placeholder)
# -----------------------------
class TokenBucket:
    def __init__(self, capacity: int = 10, refill_rate: float = 2.0):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()

    async def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

# -----------------------------
# Database Manager (SQLCipher)
# -----------------------------
class DatabaseManager:
    """
    Manages encrypted SQLite (SQLCipher) + salted hashing state.
    Tables:
      - activation_state(id=1, activated INT, activated_at TEXT)
      - banned_words(word TEXT PK)
      - violations(user_hash PK, count INT, last_violation TEXT)
      - dm_spam(user_hash PK, count INT, last_seen TEXT, actioned INT)
      - salt_state(id=1, salt TEXT, last_rotated_at TEXT)   (only if SALT not provided)
    """
    def __init__(self, db_path: Path, db_passphrase: str, initial_salt: Optional[str], rotation_enabled: bool):
        self.db_path = db_path
        self.db_passphrase = db_passphrase
        self.rotation_enabled = rotation_enabled  # True if SALT not provided (enable daily rotation)
        self.current_salt = initial_salt  # hex string
        self._init_and_load()

    def _connect(self):
        conn = sqlcipher.connect(self.db_path)
        # Apply key
        conn.execute(f"PRAGMA key='{self.db_passphrase}';")
        # Optional cipher settings (can adjust page_size/kdf_iter)
        conn.execute("PRAGMA cipher_page_size = 4096;")
        conn.execute("PRAGMA kdf_iter = 64000;")
        conn.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512;")
        conn.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512;")
        return conn

    def _init_and_load(self):
        with self._connect() as conn:
            cur = conn.cursor()
            # Core tables
            cur.execute("""
            CREATE TABLE IF NOT EXISTS activation_state(
                id INTEGER PRIMARY KEY CHECK(id=1),
                activated INTEGER NOT NULL,
                activated_at TEXT NOT NULL
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_words(
                word TEXT PRIMARY KEY
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS violations(
                user_hash TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                last_violation TEXT
            )""")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS dm_spam(
                user_hash TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                last_seen TEXT,
                actioned INTEGER DEFAULT 0
            )""")
            # Salt state only needed if rotation enabled
            if self.rotation_enabled:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS salt_state(
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    salt TEXT NOT NULL,
                    last_rotated_at TEXT NOT NULL
                )""")
                cur.execute("SELECT salt, last_rotated_at FROM salt_state WHERE id=1")
                row = cur.fetchone()
                if row is None:
                    # create new salt
                    gen = secrets.token_hex(32)
                    now = datetime.utcnow().isoformat()
                    cur.execute("INSERT INTO salt_state(id, salt, last_rotated_at) VALUES (1, ?, ?)",
                                (gen, now))
                    self.current_salt = gen
                    logger.info("Initialized rotating salt (first generation).")
                else:
                    self.current_salt = row[0]
            else:
                # activation row if missing
                pass

            cur.execute("SELECT activated FROM activation_state WHERE id=1")
            if cur.fetchone() is None:
                cur.execute("INSERT INTO activation_state(id, activated, activated_at) VALUES (1, 0, ?)",
                            (datetime.utcnow().isoformat(),))
            conn.commit()

        if not self.current_salt:
            # Edge case: rotation disabled but no SALT provided? Should not happen.
            raise ValueError("Salt initialization failed (no SALT and rotation disabled).")

    # -------- Salt rotation --------
    def rotate_salt_if_due(self) -> bool:
        """Rotate salt if rotation_enabled and >24h since last rotation. Returns True if rotated."""
        if not self.rotation_enabled:
            return False
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT salt, last_rotated_at FROM salt_state WHERE id=1")
            row = cur.fetchone()
            if not row:
                return False
            old_salt, last_rotated_at = row
            last_dt = datetime.fromisoformat(last_rotated_at)
            if datetime.utcnow() - last_dt > timedelta(days=1):
                new_salt = secrets.token_hex(32)
                cur.execute("UPDATE salt_state SET salt=?, last_rotated_at=? WHERE id=1",
                            (new_salt, datetime.utcnow().isoformat()))
                # Clear data tied to old salt (user_hash becomes obsolete)
                cur.execute("DELETE FROM violations")
                cur.execute("DELETE FROM dm_spam")
                conn.commit()
                self.current_salt = new_salt
                logger.info("Rotated salt (daily) -> violations & dm_spam reset.")
                return True
        return False

    def next_rotation_eta(self) -> Optional[str]:
        if not self.rotation_enabled:
            return None
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT last_rotated_at FROM salt_state WHERE id=1")
            row = cur.fetchone()
            if not row:
                return None
            last_dt = datetime.fromisoformat(row[0])
            nxt = last_dt + timedelta(days=1)
            return nxt.isoformat()

    # -------- Hashing (keyed blake2b) --------
    def hash_user_id(self, user_id: int) -> str:
        # Keyed blake2b (digest_size=32)
        h = blake2b(key=bytes.fromhex(self.current_salt), digest_size=32)
        h.update(str(user_id).encode())
        return h.hexdigest()

    # -------- Activation --------
    def is_activated(self) -> bool:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT activated FROM activation_state WHERE id=1")
            r = cur.fetchone()
            return bool(r and r[0] == 1)

    def set_activated(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE activation_state SET activated=1, activated_at=? WHERE id=1",
                        (datetime.utcnow().isoformat(),))
            conn.commit()

    def get_activation_row(self) -> Tuple[int, str]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT activated, activated_at FROM activation_state WHERE id=1")
            return cur.fetchone()

    # -------- Violations --------
    def add_violation(self, user_id: int) -> int:
        user_hash = self.hash_user_id(user_id)
        now = datetime.utcnow()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count, last_violation FROM violations WHERE user_hash=?", (user_hash,))
            r = cur.fetchone()
            current = 0
            if r:
                current = r[0]
                last = datetime.fromisoformat(r[1]) if r[1] else None
                if last and (now - last).days > 7:
                    current = 0
            new_count = current + 1
            cur.execute("""
                INSERT OR REPLACE INTO violations(user_hash, count, last_violation)
                VALUES (?, ?, ?)
            """, (user_hash, new_count, now.isoformat()))
            conn.commit()
            return new_count

    # -------- Banned words --------
    def get_banned_words(self) -> Set[str]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT word FROM banned_words")
            return {r[0] for r in cur.fetchall()}

    def add_banned_words(self, words: List[str]) -> Tuple[List[str], List[str]]:
        added, existing, cleaned = [], [], []
        for w in words:
            w2 = w.strip().lower()
            if w2:
                cleaned.append(w2)
        if not cleaned:
            return added, existing
        with self._connect() as conn:
            cur = conn.cursor()
            for w in cleaned:
                try:
                    cur.execute("INSERT INTO banned_words(word) VALUES (?)", (w,))
                    added.append(w)
                    logger.info(f"Added banned word: {w}")
                except sqlite3.IntegrityError:
                    existing.append(w)
            if added:
                conn.commit()
        return added, existing

    def load_initial_banned_words(self, words: Set[str]):
        if not words:
            return
        with self._connect() as conn:
            cur = conn.cursor()
            for w in words:
                cur.execute("INSERT OR IGNORE INTO banned_words(word) VALUES (?)", (w,))
            conn.commit()

    # -------- DM Spam --------
    def record_dm(self, user_id: int, window_days: int) -> Tuple[int, bool]:
        """
        Returns (new_count, action_already_taken).
        Resets count if last_seen older than window_days.
        """
        user_hash = self.hash_user_id(user_id)
        now = datetime.utcnow()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count, last_seen, actioned FROM dm_spam WHERE user_hash=?", (user_hash,))
            r = cur.fetchone()
            count = 0
            actioned = False
            if r:
                count, last_seen, actioned_flag = r
                actioned = bool(actioned_flag)
                if last_seen:
                    last_dt = datetime.fromisoformat(last_seen)
                    if (now - last_dt).days > window_days:
                        count = 0
            count += 1
            cur.execute("""
                INSERT OR REPLACE INTO dm_spam(user_hash, count, last_seen, actioned)
                VALUES (?, ?, ?, ?)
            """, (user_hash, count, now.isoformat(), 1 if actioned else 0))
            conn.commit()
            return count, actioned

    def mark_dm_spam_actioned(self, user_id: int):
        user_hash = self.hash_user_id(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE dm_spam SET actioned=1 WHERE user_hash=?", (user_hash,))
            conn.commit()

    # -------- Aggregates for status --------
    def get_violation_aggregate(self) -> int:
        now = datetime.utcnow()
        cutoff = now - timedelta(days=7)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM violations WHERE last_violation >= ?", (cutoff.isoformat(),))
            return cur.fetchone()[0]

    def get_dm_spam_aggregate(self, window_days: int) -> Dict[str, int]:
        now = datetime.utcnow()
        cutoff = now - timedelta(days=window_days)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM dm_spam
                WHERE last_seen >= ? AND actioned=1
            """, (cutoff.isoformat(),))
            actioned = cur.fetchone()[0]
            cur.execute("""
                SELECT COUNT(*) FROM dm_spam
                WHERE last_seen >= ?
            """, (cutoff.isoformat(),))
            total = cur.fetchone()[0]
        return {"actioned": actioned, "total": total}

# -----------------------------
# Telegram Bot
# -----------------------------
class TelegramAdminBot:
    HELP_TEXT = (
        "/orwell <word OR word1,word2,word3>\n"
        "/status (admin only)\n"
        "activate (if not active)\n\n"
        "Only configured admin IDs receive responses. Others are ignored silently."
    )

    def __init__(self):
        # Required core env
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.bot_token = os.getenv("BOT_TOKEN")
        if not all([self.api_id, self.api_hash, self.bot_token]):
            raise ValueError("API_ID, API_HASH, BOT_TOKEN are required.")

        # Allowed single group
        allowed_gid = os.getenv("ALLOWED_GROUP_ID")
        if not allowed_gid or not allowed_gid.isdigit():
            raise ValueError("ALLOWED_GROUP_ID must be set to the numeric Telegram group ID.")
        self.allowed_group_id = int(allowed_gid)

        # SALT config
        provided_salt = os.getenv("SALT", "").strip()
        rotation_enabled = False
        if provided_salt:
            current_salt = provided_salt
            rotation_enabled = False
            logger.info("Using fixed SALT from environment (no rotation).")
        else:
            current_salt = None  # Will be created by DB manager
            rotation_enabled = True
            logger.warning("No SALT provided: enabling daily rotating salt (violations reset on rotation).")

        # DB encryption passphrase
        db_passphrase = os.getenv("DB_PASSPHRASE", "").strip()
        if not db_passphrase:
            raise ValueError("DB_PASSPHRASE is required for SQLCipher encryption.")

        db_path = DATA_DIR / "bot.enc.db"
        self.db = DatabaseManager(
            db_path=db_path,
            db_passphrase=db_passphrase,
            initial_salt=provided_salt or current_salt,
            rotation_enabled=rotation_enabled
        )

        self.rotation_enabled = rotation_enabled

        # Admin IDs
        self.admin_ids = self._parse_admin_ids()
        if not self.admin_ids:
            logger.warning("ADMIN_USER_IDS empty or missing. No one can control the bot.")

        # DM spam config
        self.dm_spam_threshold = self._parse_int_env("DM_SPAM_THRESHOLD", 50, min_v=5, max_v=1000)
        self.dm_spam_window_days = self._parse_int_env("DM_SPAM_WINDOW_DAYS", 7, min_v=1, max_v=30)

        # Load initial banned words (if any)
        env_words = set(
            w.strip().lower()
            for w in os.getenv("BANNED_WORDS", "").split(",")
            if w.strip()
        )
        if env_words:
            self.db.load_initial_banned_words(env_words)
        self.banned_words = self.db.get_banned_words()

        self._active_cache = self.db.is_activated()
        if not self._active_cache:
            logger.info("Bot inactive: awaiting 'activate' admin DM.")

        session_path = DATA_DIR / "bot_session"
        self.client = TelegramClient(str(session_path), int(self.api_id), self.api_hash)

        self.rate_limiter = TokenBucket(capacity=10, refill_rate=2.0)

        logger.info("Bot initialized with secure configuration.")

    # ------------- Helpers -------------
    def _parse_admin_ids(self) -> Set[int]:
        raw = os.getenv("ADMIN_USER_IDS", "")
        out = set()
        for part in raw.split(","):
            p = part.strip()
            if p.isdigit():
                out.add(int(p))
        return out

    def _parse_int_env(self, name: str, default: int, min_v: int, max_v: int) -> int:
        val_raw = os.getenv(name, str(default)).strip()
        if not val_raw.isdigit():
            logger.warning(f"{name} invalid; using default {default}")
            return default
        val = int(val_raw)
        if val < min_v or val > max_v:
            logger.warning(f"{name} out of bounds ({val}); clamping to range {min_v}-{max_v}")
            val = max(min_v, min(val, max_v))
        return val

    def is_activated(self) -> bool:
        self._active_cache = self.db.is_activated()
        return self._active_cache

    async def start(self):
        await self.client.start(bot_token=self.bot_token)
        # Event handlers
        self.client.add_event_handler(self.handle_chat_actions, events.ChatAction)
        self.client.add_event_handler(self.handle_new_message, events.NewMessage)
        self.client.add_event_handler(self.handle_message_edit, events.MessageEdited)
        logger.info("Event handlers registered.")
        # Salt rotation background (if enabled)
        if self.rotation_enabled:
            asyncio.create_task(self.salt_rotation_worker())
            logger.info("Salt rotation worker started (daily).")

    async def salt_rotation_worker(self):
        while True:
            try:
                rotated = self.db.rotate_salt_if_due()
                if rotated:
                    # Refresh banned words just in case (not strictly needed)
                    self.banned_words = self.db.get_banned_words()
                await asyncio.sleep(3600)  # check hourly
            except Exception as e:
                logger.error(f"Salt rotation worker error: {e}")
                await asyncio.sleep(3600)

    # ------------- Event Handlers -------------
    async def handle_chat_actions(self, event):
        if event.chat_id != self.allowed_group_id:
            return
        if not self.is_activated():
            return
        try:
            if not hasattr(event, "action_message") or not event.action_message:
                return
            action = event.action_message.action
            if not action:
                return
            users = []
            if hasattr(action, "users"):
                users = action.users
            elif hasattr(event.action_message, "from_id") and event.action_message.from_id:
                if hasattr(event.action_message.from_id, "user_id"):
                    users = [event.action_message.from_id.user_id]
            for user_id in users:
                try:
                    user = await self.client.get_entity(user_id)
                    if getattr(user, "bot", False):
                        continue
                    if not getattr(user, "username", None):
                        logger.info(f"Kicking user {user.id} (no username)")
                        await self.kick_user(event.chat_id, user_id)
                except Exception as ex:
                    logger.error(f"Join processing error for {user_id}: {ex}")
        except Exception as e:
            logger.error(f"Error in handle_chat_actions: {e}")

    async def handle_new_message(self, event):
        if not event.is_private and event.chat_id != self.allowed_group_id:
            return
        try:
            if event.is_private:
                await self.handle_private_dm(event)
                return
            if not self.is_activated():
                return
            await self._moderate_message(event)
        except Exception as e:
            logger.error(f"Error in handle_new_message: {e}")

    async def handle_message_edit(self, event):
        # Edited messages in allowed group must be re-scanned
        if event.is_private:
            return  # we only moderate group edits
        if event.chat_id != self.allowed_group_id:
            return
        try:
            if not self.is_activated():
                return
            await self._moderate_message(event, edited=True)
        except Exception as e:
            logger.error(f"Error in handle_message_edit: {e}")

    # ------------- Moderation Core -------------
    async def _moderate_message(self, event, edited: bool = False):
        # Combine text and (optional) caption if any (Telethon raw_text usually covers)
        text = event.raw_text or ""
        if not text:
            return
        # Refresh banned words (simple approach)
        self.banned_words = self.db.get_banned_words()
        if self.contains_banned_words(text):
            user_id = self._extract_user_id(event)
            if user_id is None:
                return
            logger.info(f"Banned content ({'edited' if edited else 'new'}) from user {user_id}; deleting.")
            try:
                await event.delete()
            except Exception as e:
                logger.error(f"Failed to delete offending message: {e}")
            violation_count = self.db.add_violation(user_id)
            if violation_count == 1:
                await self._first_violation_action(event, user_id)
            elif violation_count >= 2:
                await self._second_violation_action(event, user_id)

    async def _first_violation_action(self, event, user_id: int):
        logger.info(f"First violation -> mute 12h: user {user_id}")
        await self.mute_user(event.chat_id, user_id, hours=12)
        try:
            warn = await event.respond(
                "⚠️ Banned content removed. You are muted for 12h. Second violation within 7 days => permanent ban.",
                reply_to=event.message.id if event.message else None
            )
            asyncio.create_task(self.delete_after_delay(warn, 30))
        except Exception as e:
            logger.error(f"Warning message failed: {e}")

    async def _second_violation_action(self, event, user_id: int):
        logger.info(f"Second violation -> permanent ban: user {user_id}")
        await self.ban_user(event.chat_id, user_id)

    # ------------- Private DM Handling -------------
    async def handle_private_dm(self, event):
        user_id = self._extract_user_id(event)
        if user_id is None:
            return

        # Non-admin DM spam tracking
        if user_id not in self.admin_ids:
            await self._handle_dm_spam(user_id)
            return

        text = (event.raw_text or "").strip()
        if not text:
            return
        lower = text.lower()

        if lower == "activate":
            if self.is_activated():
                await self.safe_reply(event, "Already active.")
            else:
                self.db.set_activated()
                self._active_cache = True
                logger.info(f"Activated by admin {user_id}")
                await self.safe_reply(event, "Activated.")
            return

        if lower.startswith("/orwell"):
            await self.handle_orwell(event, text)
            return

        if lower == "/status":
            await self.handle_status(event)
            return

        await self.safe_reply(event, self.HELP_TEXT)

    async def _handle_dm_spam(self, user_id: int):
        count, actioned = self.db.record_dm(user_id, self.dm_spam_window_days)
        if not actioned and count > self.dm_spam_threshold:
            logger.info(f"DM spam threshold exceeded by user {user_id}; banning from allowed group and blocking.")
            # Ban from allowed group only (single-group design)
            try:
                await self.ban_user(self.allowed_group_id, user_id)
            except Exception as e:
                logger.error(f"Failed banning spammer {user_id}: {e}")
            # Block user
            try:
                await self.client(functions.contacts.BlockRequest(user_id))
            except Exception as e:
                logger.error(f"Failed blocking user {user_id}: {e}")
            self.db.mark_dm_spam_actioned(user_id)

    # ------------- Commands -------------
    async def handle_orwell(self, event, raw: str):
        parts = raw.strip().split(maxsplit=1)
        if len(parts) == 1:
            await self.safe_reply(event, "Usage: /orwell word OR /orwell word1,word2,word3")
            return
        payload = parts[1].strip()
        tokens = [t.strip() for t in payload.split(",") if t.strip()]
        if not tokens:
            await self.safe_reply(event, "No valid words provided.")
            return
        added, existing = self.db.add_banned_words(tokens)
        self.banned_words = self.db.get_banned_words()
        segs = []
        if added:
            segs.append("Added: " + ", ".join(added))
        if existing:
            segs.append("Skipped: " + ", ".join(existing))
        if not segs:
            segs.append("No changes.")
        await self.safe_reply(event, " | ".join(segs))

    async def handle_status(self, event):
        activated, activated_at = self.db.get_activation_row()
        activation_str = "Active" if activated else "Inactive"
        banned_count = len(self.banned_words)
        vio_7d = self.db.get_violation_aggregate()
        spam_stats = self.db.get_dm_spam_aggregate(self.dm_spam_window_days)
        salt_mode = "Fixed (env)" if not self.rotation_enabled else "Rotating (24h)"
        next_rot = self.db.next_rotation_eta() if self.rotation_enabled else "N/A"

        msg = (
            "📊 Status\n"
            f"- Activation: {activation_str} (since {activated_at})\n"
            f"- Allowed group: {self.allowed_group_id}\n"
            f"- Banned words: {banned_count}\n"
            f"- Violations (last 7d messages flagged): {vio_7d}\n"
            f"- DM Spam total (window): {spam_stats['total']} | Actioned: {spam_stats['actioned']}\n"
            f"- Salt mode: {salt_mode}\n"
            f"- Next rotation (UTC): {next_rot}\n"
            f"- Hash function: keyed blake2b/256\n"
            f"- Substring scan: ENABLED\n"
        )
        await self.safe_reply(event, msg)

    # ------------- Utilities -------------
    def _extract_user_id(self, event):
        try:
            if hasattr(event.message, "from_id") and event.message.from_id:
                if hasattr(event.message.from_id, "user_id"):
                    return event.message.from_id.user_id
                if isinstance(event.message.from_id, int):
                    return event.message.from_id
        except Exception:
            return None
        return None

    async def safe_reply(self, event, text: str):
        try:
            await event.reply(text)
        except Exception as e:
            logger.error(f"Reply failed: {e}")

    def contains_banned_words(self, text: str) -> bool:
        """
        Detection:
          1. Token scan (word boundary) – exact tokens
          2. Substring scan – any banned word as substring inside the text (aggressive)
        Substring reasoning: catches attempts like splitting punctuation or adding suffix/prefix.
        False positives possible (e.g. 'classical' contains 'ass').
        """
        if not text or not self.banned_words:
            return False
        lower = text.lower()
        # Word-boundary tokens
        tokens = re.findall(r"\b\w+\b", lower)
        for t in tokens:
            if t in self.banned_words:
                return True
        # Substring fallback
        for bw in self.banned_words:
            if bw in lower:
                return True
        return False

    async def mute_user(self, chat_id: int, user_id: int, hours: int = 12):
        try:
            until = datetime.utcnow() + timedelta(hours=hours)
            rights = ChatBannedRights(
                until_date=until,
                send_messages=True,
                send_media=True,
                send_stickers=True,
                send_gifs=True,
                send_games=True,
                send_inline=True,
                embed_links=True
            )
            await self.client.edit_permissions(chat_id, user_id, rights)
        except (ChatAdminRequiredError, UserAdminInvalidError):
            logger.error(f"Missing admin perms to mute {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds}s muting {user_id}")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Mute error {user_id}: {e}")

    async def delete_after_delay(self, message, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
            await message.delete()
        except Exception as e:
            logger.error(f"Ephemeral delete failed: {e}")

    async def kick_user(self, chat_id: int, user_id: int):
        try:
            rights = ChatBannedRights(
                until_date=datetime.utcnow() + timedelta(seconds=30),
                view_messages=True
            )
            await self.client.edit_permissions(chat_id, user_id, rights)
            await asyncio.sleep(1)
            await self.client.edit_permissions(chat_id, user_id, None)
        except (ChatAdminRequiredError, UserAdminInvalidError):
            logger.error(f"Missing admin perms to kick {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds}s kicking {user_id}")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Kick error {user_id}: {e}")

    async def ban_user(self, chat_id: int, user_id: int):
        try:
            rights = ChatBannedRights(
                until_date=None,
                view_messages=True,
                send_messages=True,
                send_media=True,
                send_stickers=True,
                send_gifs=True,
                send_games=True,
                send_inline=True,
                embed_links=True
            )
            await self.client.edit_permissions(chat_id, user_id, rights)
        except (ChatAdminRequiredError, UserAdminInvalidError):
            logger.error(f"Missing admin perms to ban {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds}s banning {user_id}")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Ban error {user_id}: {e}")

    async def run(self):
        await self.start()
        await self.client.run_until_disconnected()

# -----------------------------
# Entry point
# -----------------------------
async def main():
    try:
        bot = TelegramAdminBot()
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
