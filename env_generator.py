#!/usr/bin/env python3
"""
Environment Variable Auto-Generator for XController Bot

This module automatically generates secure values for important environment variables
when they are missing or contain placeholder/invalid values.
"""

import os
import secrets
import re
from pathlib import Path
from typing import Dict, Optional, Set


class EnvGenerator:
    """Generates and manages secure environment variables."""
    
    # Placeholder values that should be replaced
    INVALID_VALUES = {
        'change_this_to_a_strong_random_passphrase',
        'your_api_hash_here',
        'your_bot_token_here',
        '1234567890:AA...your_bot_token_here',
        'strongpassphrase',
        '',
    }
    
    # Environment variables that need secure generation
    SECURE_VARS = {
        'DB_PASSPHRASE': {
            'generator': lambda: secrets.token_urlsafe(32),
            'description': 'SQLCipher database encryption passphrase',
            'required': True,
        },
        'SALT': {
            'generator': lambda: secrets.token_hex(32),
            'description': 'Fixed salt for user ID hashing (64 hex chars)',
            'required': False,  # Optional - if missing, bot uses rotating salt
        },
    }
    
    def __init__(self, env_file_path: Optional[Path] = None):
        """Initialize the environment generator.
        
        Args:
            env_file_path: Path to .env file. If None, uses .env in current directory.
        """
        self.env_file_path = env_file_path or Path('.env')
        self.current_values = {}
        self.generated_values = {}
        
    def load_env_file(self) -> Dict[str, str]:
        """Load current values from .env file.
        
        Returns:
            Dictionary of environment variable key-value pairs.
        """
        env_values = {}
        
        if not self.env_file_path.exists():
            print(f"⚠️  No .env file found at {self.env_file_path}")
            return env_values
            
        try:
            with open(self.env_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                        
                    # Parse KEY=VALUE format
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                            
                        env_values[key] = value
                        
        except Exception as e:
            print(f"❌ Error reading .env file: {e}")
            
        self.current_values = env_values
        return env_values
    
    def is_value_invalid(self, key: str, value: str) -> bool:
        """Check if a value is invalid and needs generation.
        
        Args:
            key: Environment variable name
            value: Current value
            
        Returns:
            True if value should be regenerated
        """
        if not value or value.strip() == '':
            return True
            
        # Check against known placeholder values
        if value.strip() in self.INVALID_VALUES:
            return True
            
        # Additional checks for specific variables
        if key == 'DB_PASSPHRASE':
            # Should be at least 16 characters for security
            if len(value) < 16:
                return True
                
        elif key == 'SALT':
            # Should be valid hex and at least 32 characters (16 bytes)
            if len(value) < 32:
                return True
            try:
                int(value, 16)  # Check if valid hex
            except ValueError:
                return True
                
        return False
    
    def generate_missing_values(self) -> Dict[str, str]:
        """Generate secure values for missing or invalid environment variables.
        
        Returns:
            Dictionary of newly generated values.
        """
        generated = {}
        current_env = self.load_env_file()
        
        for var_name, config in self.SECURE_VARS.items():
            current_value = current_env.get(var_name, '')
            
            if self.is_value_invalid(var_name, current_value):
                new_value = config['generator']()
                generated[var_name] = new_value
                print(f"🔐 Generated secure {var_name}: {config['description']}")
            else:
                print(f"✅ {var_name} already configured securely")
                
        self.generated_values = generated
        return generated
    
    def update_env_file(self, new_values: Dict[str, str]) -> bool:
        """Update .env file with new values.
        
        Args:
            new_values: Dictionary of environment variables to add/update
            
        Returns:
            True if update was successful
        """
        if not new_values:
            return True
            
        try:
            # Read existing content
            existing_content = []
            if self.env_file_path.exists():
                with open(self.env_file_path, 'r', encoding='utf-8') as f:
                    existing_content = f.readlines()
            
            # Track which variables we've updated
            updated_vars = set()
            
            # Update existing lines
            for i, line in enumerate(existing_content):
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                    
                if '=' in stripped:
                    key = stripped.split('=', 1)[0].strip()
                    if key in new_values:
                        existing_content[i] = f"{key}={new_values[key]}\n"
                        updated_vars.add(key)
            
            # Add new variables that weren't found
            for key, value in new_values.items():
                if key not in updated_vars:
                    existing_content.append(f"{key}={value}\n")
            
            # Write back to file
            with open(self.env_file_path, 'w', encoding='utf-8') as f:
                f.writelines(existing_content)
                
            print(f"📝 Updated .env file with {len(new_values)} secure values")
            return True
            
        except Exception as e:
            print(f"❌ Error updating .env file: {e}")
            return False
    
    def ensure_secure_environment(self) -> bool:
        """Ensure all important environment variables have secure values.
        
        This is the main method that checks, generates, and updates environment variables.
        
        Returns:
            True if all required variables are now secure
        """
        print("🔍 Checking environment variables for security...")
        
        # Generate any missing/invalid values
        generated = self.generate_missing_values()
        
        if generated:
            print(f"🔧 Auto-generating {len(generated)} secure environment values...")
            
            # Update .env file
            if self.update_env_file(generated):
                # Reload environment variables for current process
                for key, value in generated.items():
                    os.environ[key] = value
                    
                print("✅ Environment variables updated successfully")
                return True
            else:
                print("❌ Failed to update .env file")
                return False
        else:
            print("✅ All environment variables are already secure")
            return True


def ensure_secure_environment(env_file_path: Optional[Path] = None) -> bool:
    """Convenience function to ensure secure environment variables.
    
    Args:
        env_file_path: Path to .env file. If None, uses .env in current directory.
        
    Returns:
        True if all required variables are secure
    """
    generator = EnvGenerator(env_file_path)
    return generator.ensure_secure_environment()


if __name__ == "__main__":
    # Test the environment generator
    print("🧪 Testing Environment Variable Generator")
    print("=" * 50)
    
    # Run the security check
    success = ensure_secure_environment()
    
    if success:
        print("🎉 Environment security check completed successfully!")
    else:
        print("⚠️  Environment security check encountered issues.")