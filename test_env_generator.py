#!/usr/bin/env python3
"""
Test script for environment variable auto-generation functionality
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from env_generator import EnvGenerator, ensure_secure_environment


def test_invalid_value_detection():
    """Test detection of invalid environment variable values."""
    print("🔄 Testing invalid value detection...")
    
    generator = EnvGenerator()
    
    # Test cases: (key, value, should_be_invalid)
    test_cases = [
        ("DB_PASSPHRASE", "change_this_to_a_strong_random_passphrase", True),
        ("DB_PASSPHRASE", "", True),
        ("DB_PASSPHRASE", "short", True),  # Too short
        ("DB_PASSPHRASE", "a_secure_passphrase_that_is_long_enough", False),
        ("SALT", "", True),
        ("SALT", "short", True),  # Too short
        ("SALT", "invalid_hex_value", True),  # Not hex
        ("SALT", "1234567890abcdef1234567890abcdef12345678", False),  # Valid hex, long enough
    ]
    
    passed = 0
    for key, value, should_be_invalid in test_cases:
        result = generator.is_value_invalid(key, value)
        if result == should_be_invalid:
            print(f"  ✅ {key}='{value}' -> invalid={result}")
            passed += 1
        else:
            print(f"  ❌ {key}='{value}' -> invalid={result} (expected {should_be_invalid})")
    
    print(f"  📊 Test results: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_env_file_parsing():
    """Test .env file parsing functionality."""
    print("🔄 Testing .env file parsing...")
    
    # Create a temporary .env file
    test_env_content = """# Test .env file
API_ID=123456
API_HASH=test_hash_value
DB_PASSPHRASE=change_this_to_a_strong_random_passphrase
SALT=
BANNED_WORDS=spam,scam

# Comment line
BOT_TOKEN="test_token_with_quotes"
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(test_env_content)
        temp_path = Path(f.name)
    
    try:
        generator = EnvGenerator(temp_path)
        values = generator.load_env_file()
        
        expected = {
            'API_ID': '123456',
            'API_HASH': 'test_hash_value',
            'DB_PASSPHRASE': 'change_this_to_a_strong_random_passphrase',
            'SALT': '',
            'BANNED_WORDS': 'spam,scam',
            'BOT_TOKEN': 'test_token_with_quotes',
        }
        
        success = True
        for key, expected_value in expected.items():
            if values.get(key) != expected_value:
                print(f"  ❌ {key}: got '{values.get(key)}', expected '{expected_value}'")
                success = False
            else:
                print(f"  ✅ {key}: '{values[key]}'")
        
        if success:
            print("  📊 .env file parsing successful")
            
        return success
        
    finally:
        # Cleanup
        temp_path.unlink()


def test_value_generation():
    """Test generation of secure values."""
    print("🔄 Testing secure value generation...")
    
    generator = EnvGenerator()
    
    # Test DB_PASSPHRASE generation
    db_pass = generator.SECURE_VARS['DB_PASSPHRASE']['generator']()
    if len(db_pass) >= 32:  # secrets.token_urlsafe(32) should give us enough length
        print(f"  ✅ DB_PASSPHRASE generated: {len(db_pass)} characters")
        db_pass_ok = True
    else:
        print(f"  ❌ DB_PASSPHRASE too short: {len(db_pass)} characters")
        db_pass_ok = False
    
    # Test SALT generation
    salt = generator.SECURE_VARS['SALT']['generator']()
    if len(salt) == 64:  # secrets.token_hex(32) should give us 64 hex chars
        try:
            int(salt, 16)  # Should be valid hex
            print(f"  ✅ SALT generated: {len(salt)} hex characters")
            salt_ok = True
        except ValueError:
            print(f"  ❌ SALT not valid hex: {salt}")
            salt_ok = False
    else:
        print(f"  ❌ SALT wrong length: {len(salt)} characters (expected 64)")
        salt_ok = False
    
    print(f"  📊 Value generation: {int(db_pass_ok) + int(salt_ok)}/2 passed")
    return db_pass_ok and salt_ok


def test_full_env_update():
    """Test the complete environment update workflow."""
    print("🔄 Testing complete environment update workflow...")
    
    # Create a temporary directory for this test
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        env_file = temp_path / '.env'
        
        # Create a test .env file with invalid values
        test_content = """# Test configuration
API_ID=123456
API_HASH=test_hash
BOT_TOKEN=test_token
DB_PASSPHRASE=change_this_to_a_strong_random_passphrase
SALT=
BANNED_WORDS=spam,scam
"""
        env_file.write_text(test_content)
        
        # Initialize generator and run security check
        generator = EnvGenerator(env_file)
        
        # Check which values are invalid
        invalid_count = 0
        current_values = generator.load_env_file()
        for var_name in generator.SECURE_VARS:
            if generator.is_value_invalid(var_name, current_values.get(var_name, '')):
                invalid_count += 1
        
        print(f"  📊 Found {invalid_count} invalid values")
        
        # Generate and update
        success = generator.ensure_secure_environment()
        
        if success:
            # Verify the file was updated
            updated_content = env_file.read_text()
            
            # Check that the original structure is preserved
            if 'API_ID=123456' in updated_content and '# Test configuration' in updated_content:
                print("  ✅ Original file structure preserved")
                structure_ok = True
            else:
                print("  ❌ Original file structure not preserved")
                structure_ok = False
            
            # Check that invalid values were replaced
            if 'change_this_to_a_strong_random_passphrase' not in updated_content:
                print("  ✅ Invalid DB_PASSPHRASE was replaced")
                db_replaced = True
            else:
                print("  ❌ Invalid DB_PASSPHRASE was not replaced")
                db_replaced = False
            
            # Verify new values are secure
            generator_new = EnvGenerator(env_file)
            new_values = generator_new.load_env_file()
            
            secure_count = 0
            for var_name in generator.SECURE_VARS:
                if not generator_new.is_value_invalid(var_name, new_values.get(var_name, '')):
                    secure_count += 1
            
            if secure_count == len(generator.SECURE_VARS):
                print(f"  ✅ All {secure_count} secure variables are now valid")
                all_secure = True
            else:
                print(f"  ❌ Only {secure_count}/{len(generator.SECURE_VARS)} secure variables are valid")
                all_secure = False
            
            final_success = structure_ok and db_replaced and all_secure
            print(f"  📊 Full workflow test: {'✅ PASSED' if final_success else '❌ FAILED'}")
            return final_success
        else:
            print("  ❌ Environment security check failed")
            return False


def main():
    """Run all tests."""
    print("🧪 Environment Variable Generator Tests")
    print("=" * 50)
    
    tests = [
        ("Invalid Value Detection", test_invalid_value_detection),
        ("Env File Parsing", test_env_file_parsing),
        ("Value Generation", test_value_generation),
        ("Full Environment Update", test_full_env_update),
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        try:
            if test_func():
                passed += 1
                print(f"   ✅ {test_name} PASSED")
            else:
                print(f"   ❌ {test_name} FAILED")
        except Exception as e:
            print(f"   ❌ {test_name} FAILED with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Overall Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed.")
        return 1


if __name__ == '__main__':
    sys.exit(main())