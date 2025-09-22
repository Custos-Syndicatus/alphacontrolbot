#!/usr/bin/env python3
"""
Test the environment generator integration with a simplified version of check_status
"""

import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def test_env_integration():
    """Test the environment variable integration without external dependencies."""
    print("🧪 Testing Environment Variable Integration")
    print("=" * 50)
    
    # Test 1: Check that env_generator can be imported
    try:
        from env_generator import ensure_secure_environment, EnvGenerator
        print("✅ env_generator module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import env_generator: {e}")
        return False
    
    # Test 2: Check current .env file status
    print("\n🔍 Checking current .env file status...")
    generator = EnvGenerator()
    current_values = generator.load_env_file()
    
    print(f"📊 Found {len(current_values)} environment variables in .env")
    
    # Test 3: Check security of current values
    secure_count = 0
    for var_name in generator.SECURE_VARS:
        value = current_values.get(var_name, '')
        if not generator.is_value_invalid(var_name, value):
            secure_count += 1
            print(f"✅ {var_name}: secure")
        else:
            print(f"⚠️  {var_name}: needs generation")
    
    print(f"📊 Security status: {secure_count}/{len(generator.SECURE_VARS)} variables are secure")
    
    # Test 4: Test the ensure function
    print("\n🔧 Testing ensure_secure_environment...")
    success = ensure_secure_environment()
    
    if success:
        print("✅ ensure_secure_environment completed successfully")
    else:
        print("❌ ensure_secure_environment failed")
        return False
    
    # Test 5: Verify all values are now secure
    print("\n🔍 Verifying all values are now secure...")
    generator_check = EnvGenerator()
    new_values = generator_check.load_env_file()
    
    all_secure = True
    for var_name in generator_check.SECURE_VARS:
        value = new_values.get(var_name, '')
        if generator_check.is_value_invalid(var_name, value):
            print(f"❌ {var_name}: still not secure")
            all_secure = False
        else:
            print(f"✅ {var_name}: now secure")
    
    if all_secure:
        print("\n🎉 All security-critical environment variables are now secure!")
        return True
    else:
        print("\n⚠️  Some variables are still not secure")
        return False


def test_dotenv_independence():
    """Test that the env generator works independently of python-dotenv."""
    print("\n🔄 Testing independence from python-dotenv...")
    
    # The env_generator should work even without python-dotenv installed
    try:
        from env_generator import EnvGenerator
        generator = EnvGenerator()
        
        # Load .env file manually (without dotenv)
        values = generator.load_env_file()
        
        if len(values) > 0:
            print(f"✅ Can read .env file independently: {len(values)} variables found")
            return True
        else:
            print("⚠️  No variables found in .env file")
            return False
            
    except Exception as e:
        print(f"❌ Failed to work independently: {e}")
        return False


def test_placeholder_detection():
    """Test detection of placeholder values that should be replaced."""
    print("\n🔍 Testing placeholder value detection...")
    
    from env_generator import EnvGenerator
    generator = EnvGenerator()
    
    test_cases = [
        ('DB_PASSPHRASE', 'change_this_to_a_strong_random_passphrase', True),
        ('DB_PASSPHRASE', 'strongpassphrase', True),
        ('DB_PASSPHRASE', '', True),
        ('SALT', '', True),
        ('SALT', 'short', True),
    ]
    
    passed = 0
    for var_name, value, should_be_invalid in test_cases:
        result = generator.is_value_invalid(var_name, value)
        if result == should_be_invalid:
            print(f"✅ {var_name}='{value}' -> correctly detected as {'invalid' if result else 'valid'}")
            passed += 1
        else:
            print(f"❌ {var_name}='{value}' -> incorrectly detected as {'invalid' if result else 'valid'}")
    
    print(f"📊 Placeholder detection: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def main():
    """Run all integration tests."""
    print("🧪 Environment Variable Integration Tests")
    print("=" * 60)
    
    tests = [
        ("Environment Integration", test_env_integration),
        ("Dotenv Independence", test_dotenv_independence),
        ("Placeholder Detection", test_placeholder_detection),
    ]
    
    passed = 0
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 40)
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Overall Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All integration tests passed!")
        return 0
    else:
        print("⚠️  Some integration tests failed.")
        return 1


if __name__ == '__main__':
    sys.exit(main())