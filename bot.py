#!/usr/bin/env python3
"""
Telegram Admin Bot - XController (Enhanced)

Features:
1. Auto-kick new members without username (only after activation)
2. Filter banned words from messages (only after activation)
3. Clean up / moderate (progressive enforcement: delete+mute -> ban)
4. Admin-only DM control (ONLY UIDs in ADMIN_USER_IDS; bot replies to nobody else)
5. Activation gate: bot does nothing in groups until an admin DM's 'activate'
6. /orwell multi-add: /orwell word OR /orwell word1,word2,word3
7. Auto-generate volatile SALT if absent (hash instability warning)
"""

import os
import re
import logging
import asyncio
import sqlite3
import hashlib
import hmac
import time
import secrets
from typing import Set, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import (
    ChatBannedRights,
)
from telethon.errors import (
    ChatAdminRequiredError,
    UserAdminInvalidError,
    FloodWaitError
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ----------------------------
# Data directory resolution
# ----------------------------
def get_data_dir() -> Path:
    """Get data directory with fallback logic"""
    data_dir = Path("/data")
    if data_dir.exists() and data_dir.is_dir():
        try:
            test_file = data_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return data_dir
        except (PermissionError, OSError):
            pass
    fallback_dir = Path("./data")
    fallback_dir.mkdir(exist_ok=True)
    return fallback_dir

DATA_DIR = get_data_dir()

# ----------------------------
# Logging
# ----------------------------
log_file = DATA_DIR / "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("xcontroller")
logger.info(f"Using data directory: {DATA_DIR}")

# ----------------------------
# Rate limiting
# ----------------------------
class TokenBucket:
    """Token bucket implementation for rate limiting"""
    def __init__(self, capacity: int = 10, refill_rate: float = 2.0):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()

    async def consume(self, tokens: int = 1) -> bool:
        now = time.time()
        time_passed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + (time_passed * self.refill_rate))
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    async def wait_for_token(self):
        while not await self.consume():
            await asyncio.sleep(0.1)

# ----------------------------
# Database Manager
# ----------------------------
class DatabaseManager:
    """Manage SQLite database operations & activation state"""
    def __init__(self, db_path: Path, salt: str):
        self.db_path = db_path
        self.salt = salt.encode()
        self.init_database()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def hash_user_id(self, user_id: int) -> str:
        return hmac.new(self.salt, str(user_id).encode(), hashlib.sha256).hexdigest()

    def init_database(self):
        with self._connect() as conn:
            cur = conn.cursor()
            # Violations
            cur.execute("""
                CREATE TABLE IF NOT EXISTS violations (
                    user_hash TEXT PRIMARY KEY,
                    count INTEGER DEFAULT 0,
                    last_violation TIMESTAMP
                )
            """)
            # Banned words
            cur.execute("""
                CREATE TABLE IF NOT EXISTS banned_words (
                    word TEXT PRIMARY KEY
                )
            """)
            # Activation state
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activation_state (
                    id INTEGER PRIMARY KEY CHECK (id=1),
                    activated INTEGER NOT NULL,
                    activated_at TIMESTAMP NOT NULL
                )
            """)
            # Ensure single row
            cur.execute("SELECT activated FROM activation_state WHERE id=1")
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO activation_state (id, activated, activated_at) VALUES (1, 0, ?)",
                    (datetime.utcnow().isoformat(),)
                )
            conn.commit()

    # Activation helpers
    def is_activated(self) -> bool:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT activated FROM activation_state WHERE id=1")
            row = cur.fetchone()
            return bool(row and row[0] == 1)

    def set_activated(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE activation_state SET activated=1, activated_at=? WHERE id=1",
                (datetime.utcnow().isoformat(),)
            )
            conn.commit()

    # Violations
    def get_user_violations(self, user_id: int) -> int:
        user_hash = self.hash_user_id(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count FROM violations WHERE user_hash = ?", (user_hash,))
            r = cur.fetchone()
            return r[0] if r else 0

    def add_violation(self, user_id: int) -> int:
        user_hash = self.hash_user_id(user_id)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count, last_violation FROM violations WHERE user_hash = ?", (user_hash,))
            r = cur.fetchone()
            current_count = 0
            if r:
                current_count = r[0]
                last_violation = datetime.fromisoformat(r[1]) if r[1] else None
                if last_violation and (datetime.now() - last_violation).days > 7:
                    current_count = 0
            new_count = current_count + 1
            cur.execute("""
                INSERT OR REPLACE INTO violations (user_hash, count, last_violation)
                VALUES (?, ?, ?)
            """, (user_hash, new_count, datetime.now().isoformat()))
            conn.commit()
            return new_count

    # Banned words
    def get_banned_words(self) -> Set[str]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT word FROM banned_words")
            return {row[0] for row in cur.fetchall()}

    def add_banned_words(self, words: List[str]) -> Tuple[List[str], List[str]]:
        added = []
        existing = []
        cleaned = []
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
                    cur.execute("INSERT INTO banned_words (word) VALUES (?)", (w,))
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
                if w:
                    cur.execute("INSERT OR IGNORE INTO banned_words (word) VALUES (?)", (w,))
            conn.commit()

# ----------------------------
# Telegram Bot
# ----------------------------
class TelegramAdminBot:
    HELP_TEXT = (
        "/orwell <word OR word1,word2,word3>\n"
        "activate  (send as plain DM if bot not active)\n\n"
        "Only listed admin IDs receive responses. Other users are ignored."
    )

    def __init__(self):
        # Required envs
        self.api_id = os.getenv("API_ID")
        self.api_hash = os.getenv("API_HASH")
        self.bot_token = os.getenv("BOT_TOKEN")

        if not all([self.api_id, self.api_hash, self.bot_token]):
            raise ValueError("Missing required env vars: API_ID, API_HASH, BOT_TOKEN")

        # SALT (optional)
        salt_env = os.getenv("SALT", "").strip()
        if not salt_env:
            salt_env = secrets.token_hex(32)
            logger.warning("SALT not set; generated volatile SALT (hash stability lost across restarts)")
        self.salt = salt_env

        # Admin IDs
        self.admin_ids = self._parse_admin_ids()
        if not self.admin_ids:
            logger.warning("ADMIN_USER_IDS not set or empty. No one can control the bot.")

        # DB
        db_path = DATA_DIR / "bot.db"
        self.db = DatabaseManager(db_path, self.salt)

        # Activation snapshot
        self._active_cache = self.db.is_activated()
        if not self._active_cache:
            logger.info("Bot inactive: waiting for admin 'activate' DM")

        # Initial banned words from env
        env_words = set(
            w.strip().lower()
            for w in os.getenv("BANNED_WORDS", "").split(",")
            if w.strip()
        )
        if env_words:
            self.db.load_initial_banned_words(env_words)

        self.banned_words = self.db.get_banned_words()

        # Telethon
        session_path = DATA_DIR / "bot_session"
        self.client = TelegramClient(str(session_path), int(self.api_id), self.api_hash)

        # Rate limiter (not heavily used yet)
        self.rate_limiter = TokenBucket(capacity=10, refill_rate=2.0)

        logger.info("Bot initialized")

    def _parse_admin_ids(self) -> Set[int]:
        raw = os.getenv("ADMIN_USER_IDS", "")
        ids = set()
        for part in raw.split(","):
            p = part.strip()
            if p.isdigit():
                try:
                    ids.add(int(p))
                except ValueError:
                    pass
        return ids

    def is_activated(self) -> bool:
        # Single source of truth is DB; cache for quick access
        self._active_cache = self.db.is_activated()
        return self._active_cache

    async def start(self):
        await self.client.start(bot_token=self.bot_token)
        self.client.add_event_handler(self.handle_chat_actions, events.ChatAction)
        self.client.add_event_handler(self.handle_new_message, events.NewMessage)
        logger.info("Event handlers registered; bot running")

    # ----------------------------
    # Event Handlers
    # ----------------------------
    async def handle_chat_actions(self, event):
        # Guard: no moderation until activated
        if not self.is_activated():
            return
        try:
            # Only process join events (kick users with no username)
            if not hasattr(event, 'action_message') or not event.action_message:
                return

            action = event.action_message.action
            users = []
            if hasattr(action, 'users'):
                users = action.users
            elif hasattr(event.action_message, 'from_id') and event.action_message.from_id:
                if hasattr(event.action_message.from_id, 'user_id'):
                    users = [event.action_message.from_id.user_id]
                else:
                    return
            else:
                return

            for user_id in users:
                try:
                    user = await self.client.get_entity(user_id)
                    if getattr(user, 'bot', False):
                        continue
                    if not getattr(user, 'username', None):
                        logger.info(f"Kicking user {user.id} (no username)")
                        await self.kick_user(event.chat_id, user_id)
                    else:
                        logger.info(f"User @{user.username} joined (has username) - allowed")
                except Exception as e:
                    logger.error(f"Error processing new member {user_id}: {e}")
        except Exception as e:
            logger.error(f"Error in handle_chat_actions: {e}")

    async def handle_new_message(self, event):
        try:
            # Distinguish private vs group
            if event.is_private:
                await self.handle_private_dm(event)
                return

            # Group message moderation only if activated
            if not self.is_activated():
                return

            # For group messages: do not reply to anyone (commands disabled for non-admin group context)
            # Refresh banned words (lightweight)
            self.banned_words = self.db.get_banned_words()
            text = event.raw_text or ""
            if not text:
                return

            if self.contains_banned_words(text):
                user_id = self._extract_user_id(event)
                if user_id is None:
                    return
                logger.info(f"Banned content detected from user {user_id}; deleting message")
                await event.delete()
                violation_count = self.db.add_violation(user_id)
                if violation_count == 1:
                    logger.info(f"First violation for {user_id}: muting 12h + warning")
                    await self.mute_user(event.chat_id, user_id, hours=12)
                    try:
                        warning_msg = await event.respond(
                            "⚠️ Banned content deleted. You are muted for 12h. Second violation in 7 days => ban.",
                            reply_to=event.message.id
                        )
                        asyncio.create_task(self.delete_after_delay(warning_msg, 30))
                    except Exception as e:
                        logger.error(f"Warn message send failed: {e}")
                elif violation_count >= 2:
                    logger.info(f"Second violation for {user_id}: banning permanently")
                    await self.ban_user(event.chat_id, user_id)
        except Exception as e:
            logger.error(f"Error in handle_new_message: {e}")

    # ----------------------------
    # Private DM handling
    # ----------------------------
    async def handle_private_dm(self, event):
        """Only admins receive responses. Non-admin DMs are ignored completely."""
        user_id = self._extract_user_id(event)
        if user_id is None:
            return
        if user_id not in self.admin_ids:
            return  # Silent ignore

        text = (event.raw_text or "").strip()
        if not text:
            return

        # Activation attempt
        if text.lower() == "activate":
            if self.is_activated():
                await self.safe_reply(event, "Already active.")
            else:
                self.db.set_activated()
                self._active_cache = True
                logger.info(f"Bot activated by admin {user_id}")
                await self.safe_reply(event, "Activated.")
            return

        # /orwell command (multi-add)
        if text.lower().startswith("/orwell"):
            await self.handle_orwell_command(event, text)
            return

        # Any other admin DM -> help
        await self.safe_reply(event, self.HELP_TEXT)

    async def handle_orwell_command(self, event, message_text: str):
        """
        /orwell <word>
        /orwell word1,word2,word3
        """
        # Remove the command token
        parts = message_text.strip().split(maxsplit=1)
        if len(parts) == 1:
            await self.safe_reply(event, "Usage: /orwell word OR /orwell word1,word2,word3")
            return
        payload = parts[1].strip()
        # Split by commas OR treat as single token
        raw_tokens = [t.strip() for t in payload.split(",")]
        tokens = [t for t in raw_tokens if t]

        if not tokens:
            await self.safe_reply(event, "No valid words provided.")
            return

        added, existing = self.db.add_banned_words(tokens)
        # Refresh in-memory cache
        self.banned_words = self.db.get_banned_words()

        segments = []
        if added:
            segments.append("Added: " + ", ".join(added))
        if existing:
            segments.append("Skipped: " + ", ".join(existing))
        if not segments:
            segments.append("No changes.")
        await self.safe_reply(event, " | ".join(segments))

    # ----------------------------
    # Utility methods
    # ----------------------------
    def _extract_user_id(self, event):
        try:
            if hasattr(event.message, 'from_id') and event.message.from_id:
                if hasattr(event.message.from_id, 'user_id'):
                    return event.message.from_id.user_id
                # Sometimes it's already an int
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
        if not text or not self.banned_words:
            return False
        text_lower = text.lower()
        # Word boundary check
        words = re.findall(r'\b\w+\b', text_lower)
        for w in words:
            if w in self.banned_words:
                return True
        # Substring fallback (optional)
        for bw in self.banned_words:
            if bw in text_lower:
                return True
        return False

    async def mute_user(self, chat_id: int, user_id: int, hours: int = 12):
        try:
            mute_until = datetime.now() + timedelta(hours=hours)
            ban_rights = ChatBannedRights(
                until_date=mute_until,
                send_messages=True,
                send_media=True,
                send_stickers=True,
                send_gifs=True,
                send_games=True,
                send_inline=True,
                embed_links=True
            )
            await self.client.edit_permissions(chat_id, user_id, ban_rights)
        except (ChatAdminRequiredError, UserAdminInvalidError):
            logger.error(f"Missing admin perms to mute {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds}s while muting")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error muting {user_id}: {e}")

    async def delete_after_delay(self, message, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
            await message.delete()
        except Exception as e:
            logger.error(f"Delay delete failed: {e}")

    async def kick_user(self, chat_id: int, user_id: int):
        try:
            ban_rights = ChatBannedRights(
                until_date=datetime.now() + timedelta(seconds=30),
                view_messages=True
            )
            await self.client.edit_permissions(chat_id, user_id, ban_rights)
            await asyncio.sleep(1)
            await self.client.edit_permissions(chat_id, user_id, None)
        except (ChatAdminRequiredError, UserAdminInvalidError):
            logger.error(f"Missing admin perms to kick {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds}s while kicking")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error kicking {user_id}: {e}")

    async def ban_user(self, chat_id: int, user_id: int):
        try:
            ban_rights = ChatBannedRights(
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
            await self.client.edit_permissions(chat_id, user_id, ban_rights)
        except (ChatAdminRequiredError, UserAdminInvalidError):
            logger.error(f"Missing admin perms to ban {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait {e.seconds}s while banning")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error banning {user_id}: {e}")

    async def run(self):
        await self.start()
        await self.client.run_until_disconnected()

# ----------------------------
# Entry point
# ----------------------------
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
