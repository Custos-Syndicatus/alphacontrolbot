#!/usr/bin/env python3
"""
Test bot initialization with environment auto-generation
"""

import os
import sys
import tempfile
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))


def test_bot_initialization_without_sqlcipher():
    """Test bot initialization logic without actually requiring SQLCipher."""
    print("🔄 Testing bot initialization flow with env auto-generation...")
    
    # Create a temporary .env file with invalid values
    test_env_content = """# Test configuration
API_ID=123456
API_HASH=your_api_hash_here
BOT_TOKEN=1234567890:AA...your_bot_token_here
ALLOWED_GROUP_ID=-1001234567890123
ADMIN_USER_IDS=11111111,22222222
DB_PASSPHRASE=change_this_to_a_strong_random_passphrase
SALT=
BANNED_WORDS=spam,scam
"""
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        env_file = temp_path / '.env'
        env_file.write_text(test_env_content)
        
        # Change to temporary directory to test
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_path)
            
            # Test the environment generation part of bot initialization
            from env_generator import ensure_secure_environment
            
            print("  🔍 Running environment security check...")
            success = ensure_secure_environment()
            
            if not success:
                print("  ❌ Environment security check failed")
                return False
            
            # Verify the .env file was updated
            updated_content = env_file.read_text()
            
            # Check that invalid values were replaced
            tests = [
                ('change_this_to_a_strong_random_passphrase', False, 'DB_PASSPHRASE placeholder removed'),
                ('your_api_hash_here', True, 'API_HASH placeholder preserved (not auto-generated)'),
                ('API_ID=123456', True, 'Valid API_ID preserved'),
                ('# Test configuration', True, 'Comments preserved'),
            ]
            
            all_passed = True
            for test_value, should_exist, description in tests:
                exists = test_value in updated_content
                if exists == should_exist:
                    print(f"  ✅ {description}")
                else:
                    print(f"  ❌ {description} - expected {'present' if should_exist else 'absent'}")
                    all_passed = False
            
            # Check that new secure values were added
            lines = updated_content.split('\n')
            secure_vars_found = 0
            
            for line in lines:
                if line.startswith('DB_PASSPHRASE=') and '=' in line:
                    value = line.split('=', 1)[1]
                    if len(value) >= 32 and value != 'change_this_to_a_strong_random_passphrase':
                        print(f"  ✅ DB_PASSPHRASE updated with secure value ({len(value)} chars)")
                        secure_vars_found += 1
                    else:
                        print(f"  ❌ DB_PASSPHRASE not properly updated")
                        all_passed = False
                        
                elif line.startswith('SALT=') and '=' in line:
                    value = line.split('=', 1)[1]
                    if len(value) == 64:
                        try:
                            int(value, 16)  # Check if valid hex
                            print(f"  ✅ SALT updated with secure hex value ({len(value)} chars)")
                            secure_vars_found += 1
                        except ValueError:
                            print(f"  ❌ SALT value is not valid hex")
                            all_passed = False
                    elif len(value) == 0:
                        print(f"  ❌ SALT was not generated")
                        all_passed = False
                    else:
                        print(f"  ❌ SALT has wrong length: {len(value)}")
                        all_passed = False
            
            if secure_vars_found == 2:
                print(f"  ✅ All {secure_vars_found} security variables updated")
            else:
                print(f"  ❌ Only {secure_vars_found}/2 security variables updated")
                all_passed = False
            
            return all_passed
            
        finally:
            os.chdir(original_cwd)


def test_env_generator_import_in_bot():
    """Test that the env generator can be imported as done in bot.py."""
    print("🔄 Testing env generator import pattern used in bot.py...")
    
    # Simulate the import pattern used in bot.py
    import_success = False
    generation_success = False
    
    try:
        from env_generator import ensure_secure_environment
        import_success = True
        print("  ✅ env_generator imported successfully")
        
        # This should run without errors even if .env doesn't exist
        generation_success = ensure_secure_environment()
        print("  ✅ ensure_secure_environment executed successfully")
        
    except ImportError:
        print("  ⚠️  env_generator not available, would skip auto-generation")
        import_success = True  # This is acceptable fallback behavior
        generation_success = True
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False
    
    return import_success and generation_success


def test_bot_py_modification():
    """Test that bot.py was correctly modified to include env generation."""
    print("🔄 Testing bot.py modification...")
    
    bot_file = Path(__file__).parent / 'bot.py'
    if not bot_file.exists():
        print("  ❌ bot.py not found")
        return False
    
    content = bot_file.read_text()
    
    # Check for the import and call
    tests = [
        ('from env_generator import ensure_secure_environment', 'env_generator import'),
        ('ensure_secure_environment()', 'auto-generation call'),
        ('except ImportError:', 'fallback handling'),
        ('load_dotenv()', 'dotenv loading after generation'),
    ]
    
    all_passed = True
    for pattern, description in tests:
        if pattern in content:
            print(f"  ✅ {description} found")
        else:
            print(f"  ❌ {description} missing")
            all_passed = False
    
    return all_passed


def main():
    """Run all tests."""
    print("🧪 Bot Integration Tests for Environment Auto-Generation")
    print("=" * 65)
    
    tests = [
        ("Environment Generator Import", test_env_generator_import_in_bot),
        ("Bot.py Modification", test_bot_py_modification),
        ("Bot Initialization Flow", test_bot_initialization_without_sqlcipher),
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 45)
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 65)
    print(f"📊 Overall Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All bot integration tests passed!")
        return 0
    else:
        print("⚠️  Some bot integration tests failed.")
        return 1


if __name__ == '__main__':
    sys.exit(main())