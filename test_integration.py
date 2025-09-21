#!/usr/bin/env python3
"""
Integration test for XController bot functionality
Tests all major components without requiring actual Telegram connection
"""

import os
import sys
import tempfile
import asyncio
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def test_data_directory():
    """Test data directory creation and fallback"""
    print("🗂️  Testing data directory management...")
    
    # Import after setting path
    from bot import get_data_dir
    
    # Test should use ./data in test environment
    data_dir = get_data_dir()
    print(f"   Data directory: {data_dir}")
    
    # Should be able to create files in data directory
    test_file = data_dir / "test.txt"
    test_file.write_text("test")
    assert test_file.exists(), "Should be able to write to data directory"
    test_file.unlink()
    
    print("   ✅ Data directory management working")

def test_database_operations():
    """Test database operations"""
    print("💾 Testing database operations...")
    
    from bot import DatabaseManager
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = Path(tmp.name)
    
    try:
        db = DatabaseManager(db_path, "test_salt_12345678")
        
        # Test violation tracking
        user_id = 12345
        count1 = db.add_violation(user_id)
        assert count1 == 1, "First violation should return 1"
        
        count2 = db.add_violation(user_id)
        assert count2 == 2, "Second violation should return 2"
        
        # Test banned words management
        assert db.add_banned_word("testword"), "Should add banned word"
        banned_words = db.get_banned_words()
        assert "testword" in banned_words, "Should contain added word"
        
        assert db.remove_banned_word("testword"), "Should remove banned word"
        banned_words = db.get_banned_words()
        assert "testword" not in banned_words, "Should not contain removed word"
        
        print("   ✅ Database operations working")
        
    finally:
        # Clean up
        if db_path.exists():
            db_path.unlink()

async def test_rate_limiting():
    """Test rate limiting functionality"""
    print("⏱️  Testing rate limiting...")
    
    from bot import TokenBucket
    
    # Test with small bucket for quick testing
    bucket = TokenBucket(capacity=3, refill_rate=10.0)  # Fast refill for testing
    
    # Should succeed initially
    for i in range(3):
        success = await bucket.consume()
        assert success, f"Token {i+1} should succeed"
    
    # Should fail when bucket is empty
    success = await bucket.consume()
    assert not success, "Token consumption should fail when bucket is empty"
    
    # Wait for partial refill
    await asyncio.sleep(0.2)  # Should refill 2 tokens
    
    # Should succeed again
    success = await bucket.consume()
    assert success, "Token consumption should succeed after refill"
    
    print("   ✅ Rate limiting working")

def test_banned_words():
    """Test banned words detection"""
    print("🚫 Testing banned words detection...")
    
    # Set up environment for bot
    os.environ['API_ID'] = '123'
    os.environ['API_HASH'] = 'test'
    os.environ['BOT_TOKEN'] = 'test'
    os.environ['SALT'] = 'test_salt_12345678'
    os.environ['BANNED_WORDS'] = 'spam,scam,virus'
    
    from bot import TelegramAdminBot
    
    # Create bot instance (won't connect)
    bot = TelegramAdminBot()
    
    # Test banned word detection
    assert bot.contains_banned_words("This is spam"), "Should detect 'spam'"
    assert bot.contains_banned_words("SPAM message"), "Should detect 'SPAM' (case insensitive)"
    assert bot.contains_banned_words("Check this scam"), "Should detect 'scam'"
    assert not bot.contains_banned_words("Hello world"), "Should not detect normal text"
    assert not bot.contains_banned_words(""), "Should handle empty text"
    
    print("   ✅ Banned words detection working")

def test_user_id_hashing():
    """Test user ID hashing security"""
    print("🔐 Testing user ID hashing...")
    
    from bot import DatabaseManager
    
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = Path(tmp.name)
    
    try:
        db = DatabaseManager(db_path, "secure_salt_12345678")
        
        user_id = 123456789
        hashed = db.hash_user_id(user_id)
        
        # Hash should be deterministic
        assert db.hash_user_id(user_id) == hashed, "Hash should be deterministic"
        
        # Hash should be different with different salt
        db2 = DatabaseManager(db_path, "different_salt_12345678")
        assert db2.hash_user_id(user_id) != hashed, "Different salt should produce different hash"
        
        # Hash should be hex string of appropriate length (SHA256 = 64 chars)
        assert len(hashed) == 64, "Hash should be 64 characters (SHA256)"
        assert all(c in '0123456789abcdef' for c in hashed), "Hash should be hex"
        
        print("   ✅ User ID hashing working")
        
    finally:
        # Clean up
        if db_path.exists():
            db_path.unlink()

async def main():
    """Run all integration tests"""
    print("🧪 XController Integration Tests")
    print("=" * 50)
    
    tests = [
        ("Data Directory", test_data_directory),
        ("Database Operations", test_database_operations),
        ("Rate Limiting", test_rate_limiting),
        ("Banned Words", test_banned_words),
        ("User ID Hashing", test_user_id_hashing),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                await test_func()
            else:
                test_func()
            passed += 1
        except Exception as e:
            print(f"   ❌ {test_name} failed: {e}")
    
    print("\n" + "=" * 50)
    print(f"Integration Tests: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All integration tests passed!")
        return 0
    else:
        print("⚠️  Some integration tests failed.")
        return 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)