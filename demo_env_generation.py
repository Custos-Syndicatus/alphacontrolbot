#!/usr/bin/env python3
"""
Demonstration of the environment variable auto-generation feature
"""

import os
import sys
import tempfile
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

def demo_auto_generation():
    """Demonstrate the auto-generation feature with a realistic example."""
    print("🧪 Environment Variable Auto-Generation Demo")
    print("=" * 60)
    
    # Create a demo .env file with typical placeholder values
    demo_env_content = """# XController Bot Configuration
# Copy .env.example to .env and configure these values

# Telegram API credentials (get from https://my.telegram.org/apps)
API_ID=123456
API_HASH=your_api_hash_here
BOT_TOKEN=1234567890:AA...your_bot_token_here

# Target group configuration
ALLOWED_GROUP_ID=-1001234567890123
ADMIN_USER_IDS=11111111,22222222

# Security configuration
DB_PASSPHRASE=change_this_to_a_strong_random_passphrase
SALT=

# Optional settings
BANNED_WORDS=spam,scam,fraud
DM_SPAM_THRESHOLD=50
DM_SPAM_WINDOW_DAYS=7
"""
    
    print("📝 Creating demo .env file with placeholder values...")
    print("\nOriginal .env content:")
    print("-" * 40)
    print(demo_env_content)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        env_file = temp_path / '.env'
        env_file.write_text(demo_env_content)
        
        # Change to temporary directory
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_path)
            
            print("\n🔧 Running automatic environment variable generation...")
            print("-" * 40)
            
            from env_generator import ensure_secure_environment
            success = ensure_secure_environment()
            
            if success:
                print("\n📝 Updated .env content:")
                print("-" * 40)
                updated_content = env_file.read_text()
                print(updated_content)
                
                # Analyze what changed
                print("\n📊 Analysis of changes:")
                print("-" * 40)
                
                lines = updated_content.split('\n')
                for line in lines:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key == 'DB_PASSPHRASE':
                            if value != 'change_this_to_a_strong_random_passphrase':
                                print(f"✅ {key}: Replaced placeholder with secure {len(value)}-character value")
                            else:
                                print(f"⚠️  {key}: Placeholder not replaced")
                                
                        elif key == 'SALT':
                            if value and len(value) == 64:
                                try:
                                    int(value, 16)
                                    print(f"✅ {key}: Generated secure 64-character hex value")
                                except ValueError:
                                    print(f"⚠️  {key}: Generated value is not valid hex")
                            elif not value:
                                print(f"⚠️  {key}: Still empty")
                            else:
                                print(f"⚠️  {key}: Unexpected value length: {len(value)}")
                                
                        elif key in ['API_ID', 'API_HASH', 'BOT_TOKEN']:
                            if 'your_' in value or 'AA...' in value:
                                print(f"💡 {key}: Placeholder preserved (requires manual configuration)")
                            else:
                                print(f"✅ {key}: Already configured")
                                
                print("\n🎯 Summary:")
                print("-" * 40)
                print("✅ Security-critical values automatically generated")
                print("💡 User-specific values preserved for manual configuration")  
                print("📝 File structure and comments maintained")
                print("🔐 Generated values are cryptographically secure")
                
                return True
            else:
                print("❌ Auto-generation failed")
                return False
                
        finally:
            os.chdir(original_cwd)


def demo_detection_logic():
    """Demonstrate the detection logic for invalid values."""
    print("\n🔍 Placeholder Detection Logic Demo")
    print("=" * 60)
    
    from env_generator import EnvGenerator
    generator = EnvGenerator()
    
    test_cases = [
        ("DB_PASSPHRASE", "change_this_to_a_strong_random_passphrase", "Common placeholder"),
        ("DB_PASSPHRASE", "strongpassphrase", "Weak example value"),
        ("DB_PASSPHRASE", "", "Empty value"),
        ("DB_PASSPHRASE", "short", "Too short (< 16 chars)"),
        ("DB_PASSPHRASE", "this_is_a_secure_passphrase_with_enough_length", "Good value"),
        ("SALT", "", "Empty value"),
        ("SALT", "short", "Too short"),
        ("SALT", "invalid_hex_string", "Invalid hex"),
        ("SALT", "1234567890abcdef1234567890abcdef12345678", "Valid hex (40 chars)"),
    ]
    
    print("Testing various values to show detection logic:\n")
    
    for var_name, test_value, description in test_cases:
        is_invalid = generator.is_value_invalid(var_name, test_value)
        status = "❌ INVALID (will be regenerated)" if is_invalid else "✅ VALID (will be preserved)"
        print(f"{var_name:<15} = '{test_value:<45}' → {status}")
        print(f"                  ({description})")
        print()
    
    print("📋 Detection Rules:")
    print("-" * 20)
    print("• DB_PASSPHRASE: Must be ≥16 characters and not a known placeholder")
    print("• SALT: Must be ≥32 characters of valid hexadecimal")
    print("• Empty or whitespace-only values are always invalid")
    print("• Known placeholder patterns are automatically detected")


def main():
    """Run the demonstration."""
    try:
        # Run the main demo
        success = demo_auto_generation()
        
        # Show detection logic
        demo_detection_logic()
        
        print("\n" + "=" * 60)
        if success:
            print("🎉 Demo completed successfully!")
            print("\n💡 Key Benefits:")
            print("   • Users don't need to remember to replace all placeholders")
            print("   • Automatically ensures minimum security standards")  
            print("   • Generated values persist across bot restarts")
            print("   • Preserves manual configurations and file structure")
            return 0
        else:
            print("⚠️  Demo encountered issues")
            return 1
            
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())