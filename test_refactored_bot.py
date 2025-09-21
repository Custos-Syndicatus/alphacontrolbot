#!/usr/bin/env python3
"""
Test script for refactored XController bot functionality
Tests the new single-group focus and dynamic banned words management
"""

import os
import sys
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def test_banned_words_database():
    """Test dynamic banned words management in database"""
    print("🔄 Testing dynamic banned words management...")
    
    from bot import DatabaseManager
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = Path(tmp.name)
    
    try:
        db = DatabaseManager(db_path, "test_salt_12345678")
        
        # Test adding banned words
        assert db.add_banned_word("spam"), "Should add new word 'spam'"
        assert db.add_banned_word("scam"), "Should add new word 'scam'"
        assert not db.add_banned_word("spam"), "Should not add duplicate word 'spam'"
        
        # Test getting banned words
        banned_words = db.get_banned_words()
        assert "spam" in banned_words, "Should contain 'spam'"
        assert "scam" in banned_words, "Should contain 'scam'"
        assert len(banned_words) == 2, f"Should have 2 words, got {len(banned_words)}"
        
        # Test removing banned words
        assert db.remove_banned_word("spam"), "Should remove 'spam'"
        assert not db.remove_banned_word("spam"), "Should not remove non-existent 'spam'"
        
        banned_words = db.get_banned_words()
        assert "spam" not in banned_words, "Should not contain 'spam' after removal"
        assert "scam" in banned_words, "Should still contain 'scam'"
        
        # Test loading initial banned words
        initial_words = {"virus", "hack", "test"}
        db.load_initial_banned_words(initial_words)
        
        banned_words = db.get_banned_words()
        for word in initial_words:
            assert word in banned_words, f"Should contain initial word '{word}'"
        
        print("   ✅ Dynamic banned words management working")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    finally:
        # Cleanup
        try:
            db_path.unlink()
        except:
            pass

def test_violation_reset_logic():
    """Test 7-day violation reset logic"""
    print("🔄 Testing violation reset logic...")
    
    from bot import DatabaseManager
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = Path(tmp.name)
    
    try:
        db = DatabaseManager(db_path, "test_salt_12345678")
        
        user_id = 12345
        
        # Test first violation
        count1 = db.add_violation(user_id)
        assert count1 == 1, f"First violation should return 1, got {count1}"
        
        # Test second violation (same day)
        count2 = db.add_violation(user_id)
        assert count2 == 2, f"Second violation should return 2, got {count2}"
        
        # Simulate old violation by manually updating the timestamp
        import sqlite3
        user_hash = db.hash_user_id(user_id)
        old_date = datetime.now() - timedelta(days=8)  # 8 days ago
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE violations SET last_violation = ?, count = 1
                WHERE user_hash = ?
            ''', (old_date, user_hash))
            conn.commit()
        
        # Test violation after 7+ days should reset
        count_after_reset = db.add_violation(user_id)
        assert count_after_reset == 1, f"Violation after 8 days should reset to 1, got {count_after_reset}"
        
        print("   ✅ Violation reset logic working")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    finally:
        # Cleanup
        try:
            db_path.unlink()
        except:
            pass

def test_bot_initialization_with_banned_words():
    """Test bot initialization with banned words from environment and database"""
    print("🔄 Testing bot initialization with banned words...")
    
    # Set up environment for bot
    os.environ['API_ID'] = '123'
    os.environ['API_HASH'] = 'test'
    os.environ['BOT_TOKEN'] = 'test'
    os.environ['SALT'] = 'test_salt_12345678'
    os.environ['BANNED_WORDS'] = 'spam,scam,virus'
    
    try:
        from bot import TelegramAdminBot
        
        # Create bot instance (won't connect)
        bot = TelegramAdminBot()
        
        # Check that banned words from environment are loaded
        assert "spam" in bot.banned_words, "Should contain 'spam' from environment"
        assert "scam" in bot.banned_words, "Should contain 'scam' from environment"
        assert "virus" in bot.banned_words, "Should contain 'virus' from environment"
        
        # Test banned word detection
        assert bot.contains_banned_words("This is spam"), "Should detect 'spam'"
        assert bot.contains_banned_words("VIRUS alert"), "Should detect 'VIRUS' (case insensitive)"
        assert not bot.contains_banned_words("Hello world"), "Should not detect normal text"
        
        # Test adding a new banned word via database
        assert bot.db.add_banned_word("newword"), "Should add new word via database"
        
        # Refresh banned words and test
        bot.banned_words = bot.db.get_banned_words()
        assert "newword" in bot.banned_words, "Should contain newly added word"
        assert bot.contains_banned_words("This contains newword"), "Should detect newly added word"
        
        print("   ✅ Bot initialization with banned words working")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

async def test_orwell_command_parsing():
    """Test /orwell command parsing (without actual Telegram interaction)"""
    print("🔄 Testing /orwell command parsing...")
    
    # Set up environment for bot
    os.environ['API_ID'] = '123'
    os.environ['API_HASH'] = 'test'
    os.environ['BOT_TOKEN'] = 'test'
    os.environ['SALT'] = 'test_salt_12345678'
    os.environ['BANNED_WORDS'] = 'spam,scam'
    
    try:
        from bot import TelegramAdminBot
        
        # Create bot instance
        bot = TelegramAdminBot()
        
        # Test command parsing by checking method exists
        assert hasattr(bot, 'handle_orwell_command'), "Should have handle_orwell_command method"
        
        # Test database operations that the command would use
        initial_count = len(bot.db.get_banned_words())
        
        # Test add operation
        bot.db.add_banned_word("testword")
        new_count = len(bot.db.get_banned_words())
        assert new_count == initial_count + 1, "Should increase count after adding word"
        
        # Test remove operation
        bot.db.remove_banned_word("testword")
        final_count = len(bot.db.get_banned_words())
        assert final_count == initial_count, "Should return to original count after removing word"
        
        print("   ✅ /orwell command structure working")
        return True
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 Refactored XController Tests")
    print("=" * 50)
    
    tests = [
        ("Banned Words Database", test_banned_words_database),
        ("Violation Reset Logic", test_violation_reset_logic),
        ("Bot Initialization", test_bot_initialization_with_banned_words),
        ("Orwell Command", test_orwell_command_parsing),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
        except Exception as e:
            print(f"   ❌ Failed with error: {e}")
    
    print("\n" + "=" * 50)
    print(f"Tests: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed.")
        return 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)