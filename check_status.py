#!/usr/bin/env python3
"""
XController Bot Status Checker
Validates configuration and checks if the bot can start
"""

import os
import sys
from dotenv import load_dotenv

def check_environment():
    """Check if all required environment variables are set"""
    print("🔍 Checking environment configuration...")
    
    load_dotenv()
    
    required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("💡 Please copy .env.example to .env and configure your settings")
        return False
    
    print("✅ All required environment variables are set")
    
    # Check optional variables
    banned_words = os.getenv('BANNED_WORDS', '')
    if banned_words:
        words = [w.strip() for w in banned_words.split(',') if w.strip()]
        print(f"📝 Banned words configured: {len(words)} words")
    else:
        print("⚠️  No banned words configured")
    
    group_id = os.getenv('GROUP_ID')
    if group_id:
        print(f"🎯 Specific group ID configured: {group_id}")
    else:
        print("🌐 Bot will monitor all groups it's added to")
    
    return True

def check_dependencies():
    """Check if required Python packages are installed"""
    print("\n📦 Checking dependencies...")
    
    try:
        import telethon
        print(f"✅ telethon: {telethon.__version__}")
    except ImportError:
        print("❌ telethon not installed. Run: pip install telethon")
        return False
    
    try:
        import dotenv
        print(f"✅ python-dotenv: installed")
    except ImportError:
        print("❌ python-dotenv not installed. Run: pip install python-dotenv")
        return False
    
    return True

def check_bot_syntax():
    """Check if bot.py has valid syntax"""
    print("\n🔧 Checking bot syntax...")
    
    try:
        import py_compile
        py_compile.compile('bot.py', doraise=True)
        print("✅ Bot syntax is valid")
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error in bot.py: {e}")
        return False
    except Exception as e:
        print(f"❌ Error checking syntax: {e}")
        return False

def main():
    """Run all checks"""
    print("XController Bot Status Checker")
    print("=" * 50)
    
    checks = [
        ("Environment Configuration", check_environment),
        ("Dependencies", check_dependencies),
        ("Bot Syntax", check_bot_syntax),
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        try:
            if not check_func():
                all_passed = False
        except Exception as e:
            print(f"❌ {check_name} failed with error: {e}")
            all_passed = False
    
    print("\n" + "=" * 50)
    
    if all_passed:
        print("🎉 All checks passed! Bot is ready to run.")
        print("💡 To start the bot, run: python bot.py")
        return 0
    else:
        print("⚠️  Some checks failed. Please fix the issues above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())