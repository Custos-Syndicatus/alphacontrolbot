#!/usr/bin/env python3
"""
Telegram Admin Bot - XController
A Telegram bot for group administration with the following features:
1. Auto-kick new members without username
2. Filter banned words from messages
3. Clean up deleted accounts
4. Progressive enforcement for banned words (delete -> ban)
"""

import os
import re
import logging
import asyncio
import sqlite3
import hashlib
import hmac
import time
from typing import Dict, Set, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from telethon import TelegramClient, events
from telethon.tl.types import (
    ChatBannedRights, 
    User,
    MessageService,
    MessageActionChatAddUser,
    MessageActionChatJoinedByLink
)
from telethon.errors import (
    ChatAdminRequiredError,
    UserAdminInvalidError,
    FloodWaitError
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup data directory with fallback
def get_data_dir() -> Path:
    """Get data directory with fallback logic"""
    data_dir = Path("/data")
    if data_dir.exists() and data_dir.is_dir():
        try:
            # Test if we can write to /data
            test_file = data_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return data_dir
        except (PermissionError, OSError):
            pass
    
    # Fallback to ./data
    fallback_dir = Path("./data")
    fallback_dir.mkdir(exist_ok=True)
    return fallback_dir

DATA_DIR = get_data_dir()

# Configure logging
log_file = DATA_DIR / "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Using data directory: {DATA_DIR}")

class TokenBucket:
    """Token bucket implementation for rate limiting"""
    def __init__(self, capacity: int = 10, refill_rate: float = 2.0):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()

    async def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens, return True if successful"""
        now = time.time()
        # Add tokens based on time passed
        time_passed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + (time_passed * self.refill_rate))
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    async def wait_for_token(self):
        """Wait until a token is available"""
        while not await self.consume():
            await asyncio.sleep(0.1)

class DatabaseManager:
    """Manage SQLite database operations"""
    def __init__(self, db_path: Path, salt: str):
        self.db_path = db_path
        self.salt = salt.encode()
        self.init_database()
    
    def hash_user_id(self, user_id: int) -> str:
        """Hash user ID using HMAC-SHA256"""
        return hmac.new(self.salt, str(user_id).encode(), hashlib.sha256).hexdigest()
    
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Violations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS violations (
                    user_hash TEXT PRIMARY KEY,
                    count INTEGER DEFAULT 0,
                    last_violation TIMESTAMP
                )
            ''')
            
            # Banned words table for dynamic management
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS banned_words (
                    word TEXT PRIMARY KEY
                )
            ''')
            
            conn.commit()
    
    def get_user_violations(self, user_id: int) -> int:
        """Get violation count for user"""
        user_hash = self.hash_user_id(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT count FROM violations WHERE user_hash = ?', (user_hash,))
            result = cursor.fetchone()
            return result[0] if result else 0
    
    def add_violation(self, user_id: int) -> int:
        """Add violation for user and return new count, with 7-day reset logic"""
        user_hash = self.hash_user_id(user_id)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get current violation data
            cursor.execute('''
                SELECT count, last_violation FROM violations WHERE user_hash = ?
            ''', (user_hash,))
            result = cursor.fetchone()
            
            current_count = 0
            if result:
                current_count = result[0]
                last_violation = datetime.fromisoformat(result[1]) if result[1] else None
                
                # Reset count if more than 7 days have passed since last violation
                if last_violation and (datetime.now() - last_violation).days > 7:
                    current_count = 0
            
            new_count = current_count + 1
            
            cursor.execute('''
                INSERT OR REPLACE INTO violations (user_hash, count, last_violation)
                VALUES (?, ?, ?)
            ''', (user_hash, new_count, datetime.now()))
            conn.commit()
            return new_count
    
    def get_banned_words(self) -> set:
        """Get all banned words from database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT word FROM banned_words')
            return {row[0] for row in cursor.fetchall()}
    
    def add_banned_word(self, word: str) -> bool:
        """Add a banned word to database, returns True if added, False if already exists"""
        word = word.strip().lower()
        if not word:
            return False
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO banned_words (word) VALUES (?)', (word,))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # Word already exists
    
    def remove_banned_word(self, word: str) -> bool:
        """Remove a banned word from database, returns True if removed, False if not found"""
        word = word.strip().lower()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM banned_words WHERE word = ?', (word,))
            conn.commit()
            return cursor.rowcount > 0
    
    def load_initial_banned_words(self, words: set):
        """Load initial banned words from environment into database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for word in words:
                if word:  # Skip empty words
                    cursor.execute('INSERT OR IGNORE INTO banned_words (word) VALUES (?)', (word,))
            conn.commit()
    


class TelegramAdminBot:
    def __init__(self):
        # Environment variables
        self.api_id = os.getenv('API_ID')
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        self.salt = os.getenv('SALT')
        
        # Validate required environment variables
        if not all([self.api_id, self.api_hash, self.bot_token, self.salt]):
            raise ValueError("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN, SALT")
        
        # Initialize database
        db_path = DATA_DIR / "bot.db"
        self.db = DatabaseManager(db_path, self.salt)
        
        # Load banned words from environment and database
        banned_words_str = os.getenv('BANNED_WORDS', '')
        env_banned_words = set(word.strip().lower() for word in banned_words_str.split(',') if word.strip())
        
        # Load initial banned words into database if any exist in environment
        if env_banned_words:
            self.db.load_initial_banned_words(env_banned_words)
        
        # Get all banned words from database (includes env words + any persisted ones)
        self.banned_words = self.db.get_banned_words()
        
        # Initialize rate limiter
        self.rate_limiter = TokenBucket(capacity=10, refill_rate=2.0)
        
        # Initialize Telethon client with data directory
        session_path = DATA_DIR / "bot_session"
        self.client = TelegramClient(str(session_path), int(self.api_id), self.api_hash)
        
        logger.info("Bot initialized successfully")
    
    async def start(self):
        """Start the bot and register event handlers"""
        await self.client.start(bot_token=self.bot_token)
        logger.info("Bot started successfully")
        
        # Register event handlers
        self.client.add_event_handler(self.handle_new_member, events.ChatAction)
        self.client.add_event_handler(self.handle_message, events.NewMessage)
        
        logger.info("Event handlers registered, bot is running...")
    

    async def handle_new_member(self, event):
        """Handle new members joining the group"""
        try:
            # Check if this is a user join event
            if not hasattr(event, 'action_message') or not event.action_message:
                return
            
            action = event.action_message.action
            
            # Get the users who joined
            users = []
            if hasattr(action, 'users'):
                # Users were added by someone
                users = action.users
            elif hasattr(event.action_message, 'from_id') and event.action_message.from_id:
                # User joined by link
                users = [event.action_message.from_id.user_id if hasattr(event.action_message.from_id, 'user_id') else event.action_message.from_id]
            else:
                return
            
            for user_id in users:
                try:
                    user = await self.client.get_entity(user_id)
                    
                    # Skip if it's a bot
                    if hasattr(user, 'bot') and user.bot:
                        continue
                    
                    # Check if user has a username
                    if not hasattr(user, 'username') or not user.username:
                        logger.info(f"Kicking user {user.id} ({getattr(user, 'first_name', 'Unknown')}) - no username")
                        await self.kick_user(event.chat_id, user_id)
                    else:
                        logger.info(f"User {user.username} joined and has username - allowed")
                        
                except Exception as e:
                    logger.error(f"Error processing new member {user_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in handle_new_member: {e}")
    
    async def handle_message(self, event):
        """Handle new messages and check for banned words"""
        try:
            # Skip if message is from a bot, service message, or has no sender
            if (not hasattr(event.message, 'from_id') or 
                not event.message.from_id or 
                hasattr(event.message, 'service')):
                return
            
            # Get user ID safely
            user_id = None
            if hasattr(event.message.from_id, 'user_id'):
                user_id = event.message.from_id.user_id
            elif isinstance(event.message.from_id, int):
                user_id = event.message.from_id
            else:
                return
            
            message_text = event.message.text
            
            if not message_text:
                return
            
            # Handle /id command
            if message_text.strip().lower() == '/id':
                try:
                    await event.reply(f"Chat ID: {event.chat_id}")
                    return
                except Exception as e:
                    logger.error(f"Error responding to /id command: {e}")
                    return
            
            # Handle /orwell command for admins (DM only)
            if event.is_private and message_text.strip().lower().startswith('/orwell'):
                await self.handle_orwell_command(event, message_text)
                return
            
            # Check for banned words (refresh banned words from database)
            self.banned_words = self.db.get_banned_words()
            
            if self.contains_banned_words(message_text):
                logger.info(f"Banned word detected in message from user {user_id}")
                
                # Delete the message
                await event.delete()
                
                # Track violations in database
                violation_count = self.db.add_violation(user_id)
                
                if violation_count == 1:
                    # First violation - delete + 12h mute + ephemeral warning
                    logger.info(f"First violation for user {user_id} - deleting message, applying 12h mute, sending warning")
                    
                    # Apply 12-hour mute
                    await self.mute_user(event.chat_id, user_id, hours=12)
                    
                    # Send ephemeral warning (reply that will be auto-deleted)
                    try:
                        warning_msg = await event.respond(
                            f"⚠️ Warning: Your message contained banned content and has been deleted. "
                            f"You have been muted for 12 hours. A second violation within 7 days will result in a ban.",
                            reply_to=event.message.id
                        )
                        # Delete warning after 30 seconds
                        asyncio.create_task(self.delete_after_delay(warning_msg, 30))
                    except Exception as e:
                        logger.error(f"Error sending warning message: {e}")
                        
                elif violation_count >= 2:
                    # Second+ violation within 7 days - ban
                    logger.info(f"Second violation for user {user_id} within 7 days - banning user")
                    await self.ban_user(event.chat_id, user_id)
                    
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
    
    async def handle_orwell_command(self, event, message_text: str):
        """Handle /orwell command for managing banned words"""
        try:
            parts = message_text.strip().split()
            if len(parts) < 2:
                await event.reply(
                    "📝 **Banned Words Management**\n\n"
                    "Commands:\n"
                    "• `/orwell list` - Show all banned words\n"
                    "• `/orwell add <word>` - Add a banned word\n"
                    "• `/orwell remove <word>` - Remove a banned word\n"
                    "• `/orwell count` - Show number of banned words"
                )
                return
            
            command = parts[1].lower()
            
            if command == "list":
                banned_words = self.db.get_banned_words()
                if banned_words:
                    words_list = sorted(banned_words)
                    # Split into chunks to avoid message length limits
                    chunk_size = 50
                    for i in range(0, len(words_list), chunk_size):
                        chunk = words_list[i:i+chunk_size]
                        await event.reply(f"🚫 **Banned Words ({i+1}-{min(i+chunk_size, len(words_list))} of {len(words_list)}):**\n\n" + ", ".join(chunk))
                else:
                    await event.reply("📝 No banned words configured.")
            
            elif command == "add":
                if len(parts) < 3:
                    await event.reply("❌ Usage: `/orwell add <word>`")
                    return
                
                word = parts[2].strip().lower()
                if self.db.add_banned_word(word):
                    # Refresh the bot's banned words cache
                    self.banned_words = self.db.get_banned_words()
                    await event.reply(f"✅ Added banned word: `{word}`")
                else:
                    await event.reply(f"⚠️ Word `{word}` is already banned.")
            
            elif command == "remove":
                if len(parts) < 3:
                    await event.reply("❌ Usage: `/orwell remove <word>`")
                    return
                
                word = parts[2].strip().lower()
                if self.db.remove_banned_word(word):
                    # Refresh the bot's banned words cache
                    self.banned_words = self.db.get_banned_words()
                    await event.reply(f"✅ Removed banned word: `{word}`")
                else:
                    await event.reply(f"⚠️ Word `{word}` is not in the banned list.")
            
            elif command == "count":
                count = len(self.db.get_banned_words())
                await event.reply(f"📊 Total banned words: {count}")
            
            else:
                await event.reply("❌ Unknown command. Use `/orwell` for help.")
        
        except Exception as e:
            logger.error(f"Error in handle_orwell_command: {e}")
            await event.reply("❌ An error occurred while processing the command.")

    async def mute_user(self, chat_id: int, user_id: int, hours: int = 12):
        """Mute a user for specified hours"""
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
            logger.error(f"Bot lacks admin permissions to mute user {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait error, waiting {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error muting user {user_id}: {e}")

    async def delete_after_delay(self, message, delay_seconds: int):
        """Delete a message after specified delay"""
        try:
            await asyncio.sleep(delay_seconds)
            await message.delete()
        except Exception as e:
            logger.error(f"Error deleting delayed message: {e}")
    
    
    def contains_banned_words(self, text: str) -> bool:
        """Check if text contains any banned words"""
        if not text or not self.banned_words:
            return False
        
        text_lower = text.lower()
        
        # Check for exact word matches
        words = re.findall(r'\b\w+\b', text_lower)
        for word in words:
            if word in self.banned_words:
                return True
        
        # Check for substring matches
        for banned_word in self.banned_words:
            if banned_word in text_lower:
                return True
        
        return False
    
    async def kick_user(self, chat_id: int, user_id: int):
        """Kick a user from the group"""
        try:
            # Ban user temporarily (this kicks them)
            ban_rights = ChatBannedRights(
                until_date=datetime.now() + timedelta(seconds=30),
                view_messages=True
            )
            await self.client.edit_permissions(chat_id, user_id, ban_rights)
            
            # Immediately unban them (so they can rejoin later)
            await asyncio.sleep(1)
            await self.client.edit_permissions(chat_id, user_id, None)
            
        except (ChatAdminRequiredError, UserAdminInvalidError):
            logger.error(f"Bot lacks admin permissions to kick user {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait error, waiting {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error kicking user {user_id}: {e}")


    async def ban_user(self, chat_id: int, user_id: int):
        """Ban a user from the group permanently"""
        try:
            ban_rights = ChatBannedRights(
                until_date=None,  # Permanent ban
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
            logger.error(f"Bot lacks admin permissions to ban user {user_id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait error, waiting {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")
    

    async def run(self):
        """Run the bot indefinitely"""
        await self.start()
        await self.client.run_until_disconnected()

async def main():
    """Main function to run the bot"""
    try:
        bot = TelegramAdminBot()
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == '__main__':
    asyncio.run(main())