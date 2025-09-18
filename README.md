# XController - Telegram Admin Bot

A powerful Telegram administration bot built with Telethon that provides automated group management features.

## Features

### 🔐 Member Validation
- **Automatic Username Check**: When new members join, the bot checks if they have a username (@handle) set
- **Auto-kick**: Members without usernames are automatically kicked without notification

### 🚫 Content Moderation
- **Banned Words Filter**: Configurable list of banned words via environment variables
- **Progressive Enforcement**:
  - 1st violation: Message is deleted
  - 2nd violation: User is permanently banned

### 🧹 Maintenance
- **Deleted Account Cleanup**: Automatically removes "Deleted Account" members from groups
- **Periodic Cleanup**: Runs hourly cleanup tasks

## Setup

### Prerequisites
- Python 3.7+
- Telegram API credentials (API_ID and API_HASH)
- Bot token from @BotFather

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/AndroDoge/xcontroller.git
   cd xcontroller
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` file with your credentials:
   ```env
   API_ID=your_api_id
   API_HASH=your_api_hash
   BOT_TOKEN=your_bot_token
   BANNED_WORDS=spam,scam,virus,hack
   GROUP_ID=  # Optional: specific group ID
   ```

3. **Get Telegram API credentials**:
   - Visit https://my.telegram.org/apps
   - Create a new application to get API_ID and API_HASH

4. **Create a bot**:
   - Message @BotFather on Telegram
   - Use `/newbot` command to create a new bot
   - Get the bot token

5. **Install and run**:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

   Or manually:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python bot.py
   ```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `API_ID` | Yes | Telegram API ID from my.telegram.org |
| `API_HASH` | Yes | Telegram API Hash from my.telegram.org |
| `BOT_TOKEN` | Yes | Bot token from @BotFather |
| `BANNED_WORDS` | No | Comma-separated list of banned words |
| `GROUP_ID` | No | Specific group ID to monitor (if empty, monitors all groups) |

### Bot Permissions

The bot needs the following admin permissions in your group:
- Delete messages
- Ban users
- Add/remove users
- View member list

## Usage

1. **Add the bot to your group**
2. **Make the bot an admin** with the required permissions
3. **The bot will automatically**:
   - Check new members for usernames
   - Monitor messages for banned words
   - Clean up deleted accounts periodically

## Docker Deployment

For production deployment using Docker:

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build and run manually
docker build -t xcontroller .
docker run -d --name xcontroller --env-file .env xcontroller
```

## Logging

The bot creates detailed logs in:
- `bot.log` file for persistent logging
- Console output for real-time monitoring

## License

MIT License - see [LICENSE](LICENSE) file for details.
