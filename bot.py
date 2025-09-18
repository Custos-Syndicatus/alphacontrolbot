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
from typing import Dict, Set
from datetime import datetime, timedelta

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TelegramAdminBot:
    def __init__(self):
        # Environment variables
        self.api_id = os.getenv('API_ID')
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        self.group_id = os.getenv('GROUP_ID')
        
        # Banned words from environment
        banned_words_str = os.getenv('BANNED_WORDS', '')
        self.banned_words = set(word.strip().lower() for word in banned_words_str.split(',') if word.strip())
        
        # Track banned word violations per user
        self.user_violations: Dict[int, int] = {}
        
        # Validate required environment variables
        if not all([self.api_id, self.api_hash, self.bot_token]):
            raise ValueError("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN")
        
        # Initialize Telethon client
        self.client = TelegramClient('bot_session', int(self.api_id), self.api_hash)
        
        logger.info("Bot initialized successfully")
    
    async def start(self):
        """Start the bot and register event handlers"""
        await self.client.start(bot_token=self.bot_token)
        logger.info("Bot started successfully")
        
        # Register event handlers
        self.client.add_event_handler(self.handle_new_member, events.ChatAction)
        self.client.add_event_handler(self.handle_message, events.NewMessage)
        
        # Schedule periodic cleanup of deleted accounts
        asyncio.create_task(self.periodic_cleanup())
        
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
            
            # Check for banned words
            if self.contains_banned_words(message_text):
                logger.info(f"Banned word detected in message from user {user_id}")
                
                # Delete the message
                await event.delete()
                
                # Track violations
                self.user_violations[user_id] = self.user_violations.get(user_id, 0) + 1
                
                if self.user_violations[user_id] >= 2:
                    # Second violation - ban the user
                    logger.info(f"Banning user {user_id} for repeated banned word usage")
                    await self.ban_user(event.chat_id, user_id)
                else:
                    # First violation - just delete message
                    logger.info(f"First violation for user {user_id} - message deleted")
                    
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
    
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
    
    async def cleanup_deleted_accounts(self, chat_id: int):
        """Remove deleted accounts from the group"""
        try:
            participants = await self.client.get_participants(chat_id)
            
            for participant in participants:
                # Check if user is deleted by checking if user.deleted attribute exists and is True
                if hasattr(participant, 'deleted') and participant.deleted:
                    try:
                        logger.info(f"Removing deleted account: {participant.id}")
                        await self.kick_user(chat_id, participant.id)
                        await asyncio.sleep(1)  # Rate limiting
                    except Exception as e:
                        logger.error(f"Error removing deleted account {participant.id}: {e}")
                        
        except Exception as e:
            logger.error(f"Error in cleanup_deleted_accounts: {e}")
    
    async def periodic_cleanup(self):
        """Periodically clean up deleted accounts"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                if self.group_id:
                    # Clean up specific group
                    await self.cleanup_deleted_accounts(int(self.group_id))
                else:
                    # Clean up all groups the bot is admin in
                    async for dialog in self.client.iter_dialogs():
                        if dialog.is_group or dialog.is_channel:
                            try:
                                await self.cleanup_deleted_accounts(dialog.id)
                                await asyncio.sleep(5)  # Rate limiting between groups
                            except Exception as e:
                                logger.error(f"Error cleaning up group {dialog.id}: {e}")
                                
            except Exception as e:
                logger.error(f"Error in periodic_cleanup: {e}")
    
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