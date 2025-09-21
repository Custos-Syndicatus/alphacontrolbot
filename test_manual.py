#!/usr/bin/env python3
"""
Manual test to verify the bot functionality without connecting to Telegram
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

def test_complete_workflow():
    """Test the complete workflow"""
    print("🔄 Testing complete bot workflow...")
    
    # Set up environment
    os.environ['API_ID'] = '123456'
    os.environ['API_HASH'] = 'test_hash'
    os.environ['BOT_TOKEN'] = 'test_token'
    os.environ['SALT'] = 'test_salt_12345678'
    os.environ['BANNED_WORDS'] = 'spam,scam,virus'
    
    try:
        from bot import TelegramAdminBot, DatabaseManager
        
        print("  ✓ Creating bot instance...")
        bot = TelegramAdminBot()
        
        print("  ✓ Testing banned words detection...")
        assert bot.contains_banned_words("This is spam"), "Should detect spam"
        assert bot.contains_banned_words("VIRUS alert"), "Should detect virus (case insensitive)"
        assert not bot.contains_banned_words("Hello world"), "Should not detect clean text"
        
        print("  ✓ Testing database banned words management...")
        # Add a new word
        bot.db.add_banned_word("newbadword")
        bot.banned_words = bot.db.get_banned_words()
        assert "newbadword" in bot.banned_words, "Should contain new word"
        assert bot.contains_banned_words("This contains newbadword"), "Should detect new word"
        
        # Remove a word
        bot.db.remove_banned_word("newbadword")
        bot.banned_words = bot.db.get_banned_words()
        assert "newbadword" not in bot.banned_words, "Should not contain removed word"
        
        print("  ✓ Testing violation logic...")
        user_id = 12345
        
        # First violation
        count1 = bot.db.add_violation(user_id)
        assert count1 == 1, f"First violation should be 1, got {count1}"
        
        # Second violation (same day)
        count2 = bot.db.add_violation(user_id)
        assert count2 == 2, f"Second violation should be 2, got {count2}"
        
        print("  ✓ Testing method existence...")
        assert hasattr(bot, 'handle_orwell_command'), "Should have orwell command handler"
        assert hasattr(bot, 'mute_user'), "Should have mute_user method"
        assert hasattr(bot, 'delete_after_delay'), "Should have delete_after_delay method"
        
        # Test that old methods don't exist
        assert not hasattr(bot.db, 'is_globally_banned'), "Should not have global ban methods"
        assert not hasattr(bot.db, 'can_forward'), "Should not have forwarding methods"
        assert not hasattr(bot, 'propagate_global_ban'), "Should not have global ban methods"
        assert not hasattr(bot, 'discover_forward_groups'), "Should not have forwarding methods"
        
        print("   ✅ Complete workflow working")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

def test_env_words_to_database():
    """Test that environment banned words are properly loaded into database"""
    print("🔄 Testing environment words to database...")
    
    # Clean up any existing data
    try:
        test_db = Path("./data/bot.db")
        if test_db.exists():
            test_db.unlink()
    except:
        pass
    
    # Set up environment with specific words
    os.environ['API_ID'] = '123456'
    os.environ['API_HASH'] = 'test_hash'
    os.environ['BOT_TOKEN'] = 'test_token'
    os.environ['SALT'] = 'test_salt_12345678'
    os.environ['BANNED_WORDS'] = 'envword1,envword2,envword3'
    
    try:
        from bot import TelegramAdminBot
        
        # Create bot instance - this should load env words into database
        bot = TelegramAdminBot()
        
        # Check that environment words are in the database
        db_words = bot.db.get_banned_words()
        env_words = {'envword1', 'envword2', 'envword3'}
        
        for word in env_words:
            assert word in db_words, f"Environment word '{word}' should be in database"
            assert word in bot.banned_words, f"Environment word '{word}' should be in bot's word set"
        
        # Add a new word via database
        bot.db.add_banned_word("dynamicword")
        
        # Create a new bot instance - it should still have both env and dynamic words
        bot2 = TelegramAdminBot()
        bot2_words = bot2.db.get_banned_words()
        
        for word in env_words:
            assert word in bot2_words, f"Environment word '{word}' should persist"
        assert "dynamicword" in bot2_words, "Dynamic word should persist"
        
        print("   ✅ Environment words to database working")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

if __name__ == '__main__':
    print("🧪 Manual Bot Testing")
    print("=" * 50)
    
    tests = [
        test_complete_workflow,
        test_env_words_to_database,
    ]
    
    passed = 0
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"Manual Tests: {passed}/{len(tests)} passed")
    
    if passed == len(tests):
        print("🎉 All manual tests passed!")
    else:
        print("⚠️  Some manual tests failed.")