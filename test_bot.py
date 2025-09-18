#!/usr/bin/env python3
"""
Simple test script for XController bot functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from bot import TelegramAdminBot

def test_banned_words():
    """Test banned words detection"""
    print("Testing banned words functionality...")
    
    # Create a test instance with mock environment
    os.environ['API_ID'] = '12345'
    os.environ['API_HASH'] = 'test_hash'
    os.environ['BOT_TOKEN'] = 'test_token'
    os.environ['BANNED_WORDS'] = 'spam,scam,virus,hack'
    
    try:
        bot = TelegramAdminBot()
        
        # Test cases
        test_cases = [
            ("Hello world", False),
            ("This is spam", True),
            ("SPAM message", True),
            ("Check this scam out", True),
            ("No bad words here", False),
            ("virus alert", True),
            ("hack the system", True),
            ("spamming is bad", True),  # Contains "spam"
            ("Normal message", False),
        ]
        
        passed = 0
        total = len(test_cases)
        
        for message, should_contain_banned in test_cases:
            result = bot.contains_banned_words(message)
            if result == should_contain_banned:
                print(f"✓ '{message}' -> {result}")
                passed += 1
            else:
                print(f"✗ '{message}' -> {result} (expected {should_contain_banned})")
        
        print(f"\nTest Results: {passed}/{total} passed")
        return passed == total
        
    except Exception as e:
        print(f"Error during testing: {e}")
        return False

def test_initialization():
    """Test bot initialization"""
    print("Testing bot initialization...")
    
    # Test missing required environment variables
    old_env = os.environ.copy()
    try:
        # Clear required env vars
        for key in ['API_ID', 'API_HASH', 'BOT_TOKEN']:
            if key in os.environ:
                del os.environ[key]
        
        try:
            bot = TelegramAdminBot()
            print("✗ Should have failed with missing environment variables")
            return False
        except ValueError as e:
            print(f"✓ Correctly failed with missing env vars: {e}")
            
        # Restore and test valid initialization
        os.environ['API_ID'] = '12345'
        os.environ['API_HASH'] = 'test_hash'
        os.environ['BOT_TOKEN'] = 'test_token'
        
        bot = TelegramAdminBot()
        print("✓ Successfully initialized with valid environment variables")
        return True
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(old_env)

def main():
    """Run all tests"""
    print("XController Bot Tests")
    print("=" * 50)
    
    tests = [
        test_initialization,
        test_banned_words
    ]
    
    passed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            print()
        except Exception as e:
            print(f"Test failed with exception: {e}\n")
    
    print(f"Overall Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("All tests passed! ✓")
        return 0
    else:
        print("Some tests failed! ✗")
        return 1

if __name__ == '__main__':
    sys.exit(main())