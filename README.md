# XController - Telegram Admin Bot

A powerful Telegram administration bot built with Telethon that provides always-on automated group management with advanced features including message forwarding, global ban management, and intelligent rate limiting.

## Features

### 🔐 Member Validation
- **Automatic Username Check**: When new members join, the bot checks if they have a username (@handle) set
- **Auto-kick**: Members without usernames are automatically kicked without notification

### 🚫 Advanced Content Moderation
- **Banned Words Filter**: Configurable list of banned words via environment variables
- **Progressive Enforcement**: Database-tracked violations with global enforcement
  - 1st violation: Message is deleted
  - 2nd violation: User is globally banned across all groups
- **Global Ban Propagation**: Bans automatically propagate to all groups the bot manages (up to 20)

### 📡 Message Forwarding
- **Cross-Group Forwarding**: Forwards plain text messages to up to 20 groups
- **24-Hour Cooldown**: Per-user forwarding rate limiting to prevent spam
- **Intelligent Filtering**: Skips messages with banned words or media content
- **No Membership Requirement**: Users don't need to be members of target groups

### 🧹 Automated Maintenance
- **Deleted Account Cleanup**: Automatically removes "Deleted Account" members from groups
- **Rotating Cleanup**: Cleans one group per 12-hour cycle with pagination (25 participants per run)
- **Always-On Operation**: Continuous monitoring and maintenance

### ⚡ Performance & Security
- **Token Bucket Rate Limiting**: 10 operations capacity, 2 tokens/second refill rate
- **Secure User Tracking**: HMAC-SHA256 hashed user IDs with configurable salt
- **SQLite Persistence**: All data stored in secure, portable database
- **Data Directory Management**: Automatic /data or ./data fallback for container/local use

## Setup

### Prerequisites
- Python 3.11+
- Telegram API credentials (API_ID and API_HASH)
- Bot token from @BotFather
- Secure salt string for user ID hashing

### Local Development

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
   SALT=your_secure_random_salt_string
   BANNED_WORDS=spam,scam,virus,hack
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
| `SALT` | Yes | Secure random string for user ID hashing |
| `BANNED_WORDS` | No | Comma-separated list of banned words |

### Bot Permissions

The bot needs the following admin permissions in your groups:
- Delete messages
- Ban users
- Add/remove users
- View member list
- Send messages (for forwarding)

## Docker Deployment

### Local Docker

For local production deployment using Docker:

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build and run manually
docker build -t xcontroller .
docker run -d --name xcontroller --env-file .env -v ./data:/data xcontroller
```

### ARM64 Build

The Docker image supports multi-architecture builds including ARM64:

```bash
# Build for ARM64 (Apple Silicon, ARM-based servers)
docker buildx build --platform linux/arm64 -t xcontroller:arm64 .

# Build for both AMD64 and ARM64
docker buildx build --platform linux/amd64,linux/arm64 -t xcontroller:latest .
```

## AWS Deployment

### ECR Setup and Push

1. **Create ECR Repository**:
   ```bash
   aws ecr create-repository --repository-name xcontroller --region us-east-1
   ```

2. **Build and Push ARM64 Image**:
   ```bash
   # Get login token
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

   # Build for ARM64
   docker buildx build --platform linux/arm64 -t <account-id>.dkr.ecr.us-east-1.amazonaws.com/xcontroller:latest .

   # Push to ECR
   docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/xcontroller:latest
   ```

### ECS Fargate Deployment

1. **Create Task Definition** (`task-definition.json`):
   ```json
   {
     "family": "xcontroller-task",
     "networkMode": "awsvpc",
     "requiresCompatibilities": ["FARGATE"],
     "cpu": "256",
     "memory": "512",
     "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
     "containerDefinitions": [
       {
         "name": "xcontroller",
         "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/xcontroller:latest",
         "essential": true,
         "logConfiguration": {
           "logDriver": "awslogs",
           "options": {
             "awslogs-group": "/ecs/xcontroller",
             "awslogs-region": "us-east-1",
             "awslogs-stream-prefix": "ecs"
           }
         },
         "environment": [
           {"name": "API_ID", "value": "your_api_id"},
           {"name": "API_HASH", "value": "your_api_hash"},
           {"name": "BANNED_WORDS", "value": "spam,scam,virus,hack"}
         ],
         "secrets": [
           {
             "name": "BOT_TOKEN",
             "valueFrom": "arn:aws:secretsmanager:us-east-1:<account-id>:secret:xcontroller/bot-token"
           },
           {
             "name": "SALT",
             "valueFrom": "arn:aws:secretsmanager:us-east-1:<account-id>:secret:xcontroller/salt"
           }
         ],
         "mountPoints": [
           {
             "sourceVolume": "efs-data",
             "containerPath": "/data"
           }
         ]
       }
     ],
     "volumes": [
       {
         "name": "efs-data",
         "efsVolumeConfiguration": {
           "fileSystemId": "fs-xxxxxxxx",
           "transitEncryption": "ENABLED"
         }
       }
     ]
   }
   ```

2. **Create CloudWatch Log Group**:
   ```bash
   aws logs create-log-group --log-group-name /ecs/xcontroller --region us-east-1
   ```

3. **Store Secrets in AWS Secrets Manager**:
   ```bash
   # Store bot token
   aws secretsmanager create-secret \
     --name xcontroller/bot-token \
     --description "XController Bot Token" \
     --secret-string "your_bot_token_here" \
     --region us-east-1

   # Store salt
   aws secretsmanager create-secret \
     --name xcontroller/salt \
     --description "XController Salt for User ID Hashing" \
     --secret-string "your_secure_salt_string" \
     --region us-east-1
   ```

### Optional: EFS for Persistent Storage

For persistent data across container restarts:

1. **Create EFS File System**:
   ```bash
   aws efs create-file-system \
     --creation-token xcontroller-data \
     --throughput-mode provisioned \
     --provisioned-throughput-in-mibps 100 \
     --region us-east-1
   ```

2. **Create Mount Targets** (in your VPC subnets)
3. **Update Task Definition** with EFS volume configuration (shown above)

### Alternative: EC2 with EFS

For EC2 deployment with EFS mounting:

```bash
# Mount EFS on EC2 instance
sudo mkdir -p /data
sudo mount -t efs fs-xxxxxxxx:/ /data

# Run container with mounted directory
docker run -d --name xcontroller \
  --env-file .env \
  -v /data:/data \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/xcontroller:latest
```

## Data & Logging

### Data Directory Structure
- **Container**: Uses `/data` directory (mounted volume)
- **Local Development**: Falls back to `./data` directory if `/data` is not writable
- **Automatic Creation**: Bot creates data directory structure automatically

### Stored Data
- `bot_session*`: Telethon session files
- `bot.db`: SQLite database (violations, bans, forward state, cleanup state)
- `bot.log`: Application logs

### Log Files
- **Primary**: `/data/bot.log` (or `./data/bot.log` for local)
- **Console**: Real-time output for monitoring
- **CloudWatch**: Automatic ECS Fargate integration

## Usage

1. **Add the bot to your groups**
2. **Make the bot an admin** with required permissions in each group
3. **The bot will automatically**:
   - Discover up to 20 groups for cross-forwarding
   - Check new members for usernames
   - Monitor messages for banned words with global enforcement
   - Forward plain text messages with 24h per-user cooldowns
   - Clean up deleted accounts every 12 hours (rotating through groups)
   - Maintain persistent violation and ban tracking

## License

MIT License - see [LICENSE](LICENSE) file for details.
