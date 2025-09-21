# ⚔️ XController – Secure Telegram Moderation Bot (Single-Group, Hardened) 
# Pruned and Hardened version

> Ultra-focused, security‑centric moderation bot for ONE Telegram group.  
> Passive until explicitly activated. Encrypted, anonymized, rate-aware, salt-rotating.  
> Built for stealthy, consistent, controlled enforcement.

---

## 🚀 Core Value

| Aspect | Benefit |
|--------|---------|
| 🔐 Data Protection | Encrypted DB (SQLCipher) + keyed BLAKE2b anonymization |
| 🛡 Controlled Scope | Only acts in a single configured group (ALLOWED_GROUP_ID) |
| 🧪 Safety First | Passive until admin activates via DM |
| 🔁 Key Hygiene | Daily automatic salt rotation (if no fixed SALT provided) |
| 🔇 Silent Hardening | Ignores all non-admin DMs (unless tracking for spam) |
| 🧩 Flexible Banned Words | Multi-add with `/orwell word1,word2,...` |
| ⚠ Progressive Discipline | Delete → Mute (12h) → Permanent Ban |
| 🕵 DM Spam Defense | Silent ban/block if threshold exceeded |
| 🔄 Edited & Forwarded Message Coverage | Re-scans edits, treats forwarded message text equally |
| 📉 Minimal Disclosure | Aggregated metrics only (/status) – no user hashes shown |

---

## 🧬 Feature Overview

### Activation Gate
- State persists in encrypted DB (`activation_state`).
- Admin DM: `activate`
- Already active? Reply: `Already active.`

### Single Group Enforcement
- Strictly processes events only from `ALLOWED_GROUP_ID`.
- Any other chat → ignored (defense-in-depth).

### Message Moderation
- Scans: new messages, edited messages, forwarded messages.
- Deletes immediately on banned-word detection.
- Penalty progression (7-day window):
  1. First: delete + 12h mute + ephemeral warning (auto-deletes in 30s)
  2. Second+: permanent ban

### Banned Words
- Multi-add: `/orwell fraud, scam , spam`
- Response summary: `Added: fraud, scam | Skipped: spam`
- Detection:
  - Word boundary token match
  - Substring fallback (aggressive, catches embedded forms)
- Stored lowercased in encrypted DB.

### DM Spam Throttling
- Non-admin sending > `DM_SPAM_THRESHOLD` DMs (within `DM_SPAM_WINDOW_DAYS`) ⇒
  - Silent ban from group
  - Telegram block via Contacts.Block
  - No notification to sender
  - Count resets weekly (window-based)
- Admin DMs never counted.

### Admin Commands (DM Only)
| Command | Purpose |
|---------|---------|
| `activate` | Enable enforcement if inactive |
| `/orwell word1,word2` | Add banned words |
| `/status` | Show operational metrics |
| (anything else) | Returns help text |

### /status Output (Aggregate Only)
Shows:
- Activation state & timestamp
- Banned word count
- Violation events (7d)
- DM spam totals & actioned count
- Salt mode (Fixed vs Rotating)
- Next rotation (if rotating)
- Hash function (keyed BLAKE2b)
- Substring detection ON

No user-identifying material. No hash tokens displayed.

---

## 🔐 Security Architecture

| Layer | Mechanism | Notes |
|-------|-----------|-------|
| Data-at-Rest | SQLCipher (pysqlcipher3) | Requires `DB_PASSPHRASE` |
| Identity Privacy | Keyed BLAKE2b (digest 256-bit) | No plaintext user IDs in DB |
| Salt Strategy | Fixed (SALT env) OR rotating (24h) | Rotation clears violation + spam tables |
| Hash Rotation Impact | Fresh anonymization daily | Predictable privacy boundary |
| Scope Restriction | ALLOWED_GROUP_ID gating | Eliminates cross-group abuse |
| DM Stealth | Non-admins receive 0 responses | Reduces probing surface |
| Spam Abuse Control | Thresholded silent ban/block | No attacker feedback |
| Config Hardening | Numeric bounds & validation | Prevents extreme values |
| Logging | Operational only (no PII) | Stored in `data/bot.log` |
| Forward/Edit Coverage | Re-inspection on edit | Prevents bypass via edits |

### Salt Modes
| Mode | Trigger | Rotation | Persistence |
|------|---------|----------|------------|
| Fixed | `SALT` provided | None | Hash continuity preserved |
| Rotating | `SALT` unset | Every 24h | Violations & DM spam reset |

---

## 🧪 Substring Detection Explained

Two-tier detection:
1. Token Match: Exact token equality (fast & precise).
2. Substring Match: Banned term appears anywhere inside the lowercased text.  
   Example: banned word `fraud` flags `megaFraudster`.

Pros: catches simple obfuscations.  
Cons: can cause false positives (`classical` contains `ass`).  
(You can later make this configurable.)

---

## 🔧 Environment Variables

| Name | Required | Example | Description |
|------|----------|---------|-------------|
| API_ID | Yes | 123456 | Telegram API ID |
| API_HASH | Yes | abcd1234... | Telegram API hash |
| BOT_TOKEN | Yes | 12345:AA... | BotFather token |
| ALLOWED_GROUP_ID | Yes | -1001234567890 | Single target supergroup ID |
| ADMIN_USER_IDS | Yes (practical) | 1111,2222 | Admin numeric user IDs |
| DB_PASSPHRASE | Yes | strongpassphrase | SQLCipher encryption key |
| BANNED_WORDS | No | spam,scam | Initial banned words |
| SALT | No | 9f... | Provide to disable rotation |
| DM_SPAM_THRESHOLD | No | 50 | Non-admin DM limit (clamped 5–1000) |
| DM_SPAM_WINDOW_DAYS | No | 7 | DM spam window (1–30) |

If `SALT` omitted → rotating-salt mode engages automatically.

---

## 📦 Installation (Linux Example)

System dependencies for SQLCipher:
```bash
sudo apt update
sudo apt install -y sqlcipher libsqlcipher-dev
```

Clone & setup:
```bash
git clone https://github.com/your-org/your-repo.git
cd your-repo
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Run:
```bash
cp .env.example .env  # if you maintain one
# Edit .env with required variables
python bot.py
```

---

## 🐳 Docker Deployment

### Quick Start

**1. Clone & configure:**
```bash
git clone https://github.com/your-org/your-repo.git
cd your-repo
cp .env.example .env
```

**2. Edit `.env` with your values:**
```bash
# Required: Get from https://my.telegram.org/apps
API_ID=123456
API_HASH=your_api_hash_here
BOT_TOKEN=1234567890:AA...your_bot_token_here

# Required: Target group numeric ID
ALLOWED_GROUP_ID=-1001234567890123

# Required: Admin user IDs (comma-separated)
ADMIN_USER_IDS=11111111,22222222

# Required: Strong encryption passphrase
DB_PASSPHRASE=change_this_to_a_strong_random_passphrase
```

**3. Build & run:**
```bash
docker-compose up -d
```

### Security Best Practices

⚠️ **Critical Security Requirements:**

- **Never commit `.env` files** – Contains sensitive credentials
- **Use strong `DB_PASSPHRASE`** – If lost, data is unrecoverable  
- **Protect admin user IDs** – Only trusted users should have control
- **Secure host access** – Limit SSH/access to Docker host
- **Regular backups** – Backup `./data` directory if using fixed SALT

### Docker Commands

**Build locally:**
```bash
docker build -t xcontroller-bot .
```

**Run with custom config:**
```bash
docker run -d \
  --name xcontroller-bot \
  --env-file .env \
  -v $(pwd)/data:/data \
  xcontroller-bot
```

**View logs:**
```bash
docker-compose logs -f xcontroller
```

**Stop/start:**
```bash
docker-compose stop
docker-compose start
```

**Update & rebuild:**
```bash
docker-compose down
git pull
docker-compose up -d --build
```

### Data Persistence

- **Database**: Stored in `./data/bot.enc.db` (SQLCipher encrypted)
- **Logs**: Stored in `./data/bot.log`
- **Session**: Telegram session files in `./data/`

The `./data` directory is mounted as a Docker volume for persistence across container restarts.

### Environment Variables Reference

| Variable | Required | Description | Security Notes |
|----------|----------|-------------|----------------|
| `API_ID` | ✅ | Telegram API ID | Public, but keep secure |
| `API_HASH` | ✅ | Telegram API hash | **Secret** - never share |
| `BOT_TOKEN` | ✅ | BotFather token | **Secret** - never share |
| `ALLOWED_GROUP_ID` | ✅ | Target group ID | Public info |
| `ADMIN_USER_IDS` | ✅ | Admin user IDs | Sensitive - limit access |
| `DB_PASSPHRASE` | ✅ | Encryption key | **Critical secret** |
| `SALT` | ❌ | Fixed salt (optional) | Secret if provided |
| `BANNED_WORDS` | ❌ | Initial banned words | Operational data |

### Troubleshooting

**Container won't start:**
```bash
# Check logs
docker-compose logs xcontroller

# Check configuration
docker-compose config
```

**Database issues:**
```bash
# Check data directory permissions
ls -la ./data

# Restart with fresh database (⚠️ loses data)
rm -f ./data/bot.enc.db
docker-compose restart
```

**Network connectivity:**
```bash
# Test from inside container
docker-compose exec xcontroller ping telegram.org
```

---

## ▶ First Use Flow

1. Deploy & start (bot is INACTIVE).
2. Admin sends DM: `activate`
3. Bot replies: `Activated.`
4. Moderation begins for ALLOWED_GROUP_ID.
5. Admin adds banned words: `/orwell fraud,scam`
6. Violations appear in /status aggregate counters.

---

## 🔄 Daily Salt Rotation (if no SALT provided)
- Background task checks hourly.
- When >24h elapsed:
  - Generates new 32-byte random hex salt.
  - Clears `violations` + `dm_spam`.
  - Logs rotation event.
- /status shows next rotation ETA (UTC).

---

## 🚫 DM Spam Handling

| Condition | Action |
|-----------|--------|
| Non-admin DM count > threshold (window) | Ban from group + Block user |
| Admin DM | Never counted |
| Feedback to spammer | None (silent) |

State resets if silence > window days or salt rotation occurs.

---

## 🧩 File / Data Layout

| Path | Purpose |
|------|---------|
| `bot.py` | Main logic |
| `data/bot.enc.db` | Encrypted SQLCipher database |
| `data/bot_session*` | Telethon session |
| `data/bot.log` | Log output |

---

## 🛠 Maintenance & Operations

Action | Command / Method
-------|------------------
Add banned words | `/orwell bad1,bad2`
Check status | `/status` (admin DM)
Rotate salt manually | Remove SALT env; restart after 24h to rotate automatically
Update dependencies | Pin bump in requirements.txt
View logs | `tail -f data/bot.log`

---

## 📊 Status Example (Admin DM)
/status:
```
📊 Status
- Activation: Active (since 2025-09-21T22:00:00.000000)
- Allowed group: -1001234567890
- Banned words: 24
- Violations (last 7d messages flagged): 5
- DM Spam total (window): 3 | Actioned: 1
- Salt mode: Rotating (24h)
- Next rotation (UTC): 2025-09-22T22:00:00
- Hash function: keyed blake2b/256
- Substring scan: ENABLED
```

---

## ❓ FAQ

Q: Why are violation counts “reset”?  
A: Rotating salt mode intentionally resets identity correlation daily (privacy boundary).

Q: Can I disable rotation?  
A: Set `SALT` explicitly – rotation stops.

Q: Why not show top violators?  
A: Design choice: minimize behavioral fingerprinting exposure.

Q: False positives from substring?  
A: You can modify detection to remove substring loop if precision required.

---

## 🔍 Future (Optional Enhancements – NOT Implemented)
- Toggle for substring detection
- Export/import banned words
- Adaptive mute durations
- Hash versioning for seamless rotations
- Message pattern heuristics / ML scoring

(Left out intentionally per scope.)

---

## ⚠ Disclaimer
This bot enforces moderation logic; always verify environment configuration in restricted staging before production deployment. Encryption security depends on protecting `DB_PASSPHRASE`.

---

## 🧾 License
Add your license text here (e.g. MIT).

---

Built for precision, privacy, and resilience.  
Built with heart and Linux by AndroDoge
