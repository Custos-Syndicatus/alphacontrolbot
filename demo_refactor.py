#!/usr/bin/env python3
"""
Demo script showing the key features of the refactored bot
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

def demo_features():
    """Demonstrate the key features"""
    
    # Set up environment
    os.environ.update({
        'API_ID': '123456',
        'API_HASH': 'test_hash',
        'BOT_TOKEN': 'test_token',
        'SALT': 'demo_salt_12345678',
        'BANNED_WORDS': 'spam,scam,virus'
    })
    
    from bot import TelegramAdminBot
    
    print("🎯 REFACTORED BOT DEMO")
    print("=" * 60)
    
    # Create bot
    print("\n1️⃣ CREATING BOT INSTANCE")
    bot = TelegramAdminBot()
    print(f"   ✅ Bot initialized with {len(bot.banned_words)} banned words")
    print(f"   📝 Initial words: {sorted(bot.banned_words)}")
    
    # Demo banned words detection
    print("\n2️⃣ BANNED WORDS DETECTION")
    test_messages = [
        "Hello world",
        "This is spam",
        "VIRUS alert!",
        "Normal conversation",
        "Check this scam out"
    ]
    
    for msg in test_messages:
        detected = bot.contains_banned_words(msg)
        status = "🚫 BANNED" if detected else "✅ CLEAN"
        print(f"   {status}: '{msg}'")
    
    # Demo dynamic banned words management
    print("\n3️⃣ DYNAMIC BANNED WORDS MANAGEMENT")
    print("   Adding new words...")
    bot.db.add_banned_word("newbadword")
    bot.db.add_banned_word("anotherbad")
    
    # Refresh bot's word list
    bot.banned_words = bot.db.get_banned_words()
    print(f"   ✅ Total words now: {len(bot.banned_words)}")
    print(f"   📝 Updated list: {sorted(bot.banned_words)}")
    
    # Test new words
    print(f"   🚫 'newbadword' detected: {bot.contains_banned_words('This has newbadword')}")
    
    # Demo violation tracking with reset logic
    print("\n4️⃣ VIOLATION TRACKING WITH 7-DAY RESET")
    user_id = 12345
    
    print("   Simulating violations...")
    count1 = bot.db.add_violation(user_id)
    print(f"   📊 First violation: count = {count1}")
    
    count2 = bot.db.add_violation(user_id)  
    print(f"   📊 Second violation (same day): count = {count2}")
    
    # Simulate old violation (manual database update)
    import sqlite3
    user_hash = bot.db.hash_user_id(user_id)
    old_date = datetime.now() - timedelta(days=8)
    
    db_path = bot.db.db_path
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE violations SET last_violation = ?, count = 1
            WHERE user_hash = ?
        ''', (old_date, user_hash))
        conn.commit()
    
    count_reset = bot.db.add_violation(user_id)
    print(f"   📊 Violation after 8 days (reset): count = {count_reset}")
    
    # Demo new enforcement logic
    print("\n5️⃣ NEW ENFORCEMENT BEHAVIOR")
    print("   🥇 First violation:")
    print("      • Delete message")
    print("      • 12-hour mute")
    print("      • Ephemeral warning (auto-deleted after 30s)")
    print("   🥈 Second violation (within 7 days):")
    print("      • Permanent ban")
    print("   🔄 Reset after 7+ days with no violations")
    
    # Demo orwell command structure
    print("\n6️⃣ /ORWELL COMMAND FEATURES")
    print("   📝 Available commands (DM only):")
    print("      • /orwell list      - Show all banned words")
    print("      • /orwell add <word> - Add a banned word")  
    print("      • /orwell remove <word> - Remove a banned word")
    print("      • /orwell count     - Show number of banned words")
    
    # Demo what was removed
    print("\n7️⃣ REMOVED FUNCTIONALITY")
    print("   ❌ Global bans and propagation")
    print("   ❌ Message forwarding between groups")
    print("   ❌ Group cleanup maintenance")
    print("   ❌ Multi-group discovery and management")
    
    print("\n✨ REFACTOR COMPLETE!")
    print("   • Single-group focused moderation")
    print("   • Progressive enforcement (mute → ban)")
    print("   • Dynamic banned words management")
    print("   • Automatic violation reset")
    print("=" * 60)

if __name__ == '__main__':
    demo_features()