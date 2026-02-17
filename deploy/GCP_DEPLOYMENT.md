# Frepi Finance Bot - GCP Deployment Guide

Deploys alongside the existing procurement agent on the same GCP VM.

## Prerequisites

- GCP VM already running (`frepi-agent-vm` in `southamerica-east1`)
- Supabase database with finance migrations applied
- Telegram bot token from @BotFather

## Step 1: Upload to VM

From your local machine:

```bash
cd frepi_finance_bot
zip -r frepi-finance.zip frepi_finance deploy migrations requirements.txt pyproject.toml .env.example

gcloud compute scp frepi-finance.zip frepi-agent-vm:~ --zone=southamerica-east1-c
```

## Step 2: Install on VM

SSH into the VM:

```bash
gcloud compute ssh frepi-agent-vm --zone=southamerica-east1-c
```

Run the setup script:

```bash
unzip -o frepi-finance.zip -d frepi-finance
cd frepi-finance
chmod +x deploy/setup.sh
./deploy/setup.sh
```

## Step 3: Configure Environment

```bash
sudo nano /opt/frepi-finance/.env
```

Add your credentials:

```
OPENAI_API_KEY=sk-proj-...
SUPABASE_URL=https://oknotufkobuwpmtyslma.supabase.co
SUPABASE_KEY=eyJ...
TELEGRAM_FINANCE_BOT_TOKEN=8257569727:AAG...

ENVIRONMENT=production
LOG_LEVEL=INFO
CHAT_MODEL=gpt-4o
CMV_TARGET_PERCENT=32.0
SIGNIFICANT_PRICE_CHANGE_PERCENT=10.0
```

## Step 4: Start the Service

```bash
sudo systemctl start frepi-finance
sudo systemctl status frepi-finance
sudo journalctl -u frepi-finance -f
```

## Useful Commands

```bash
# Stop
sudo systemctl stop frepi-finance

# Restart
sudo systemctl restart frepi-finance

# Recent logs
sudo journalctl -u frepi-finance --since "1 hour ago"

# Test connection
cd /opt/frepi-finance
source venv/bin/activate
frepi-finance test

# Interactive chat
frepi-finance chat-cli
```

## Deploy Updates

From your local machine:

```bash
cd frepi_finance_bot
zip -r frepi-finance.zip frepi_finance requirements.txt
gcloud compute scp frepi-finance.zip frepi-agent-vm:~ --zone=southamerica-east1-c
```

On the VM:

```bash
cd ~
unzip -o frepi-finance.zip -d /tmp/frepi-update
sudo cp -r /tmp/frepi-update/frepi_finance /opt/frepi-finance/
sudo systemctl restart frepi-finance
sudo journalctl -u frepi-finance -f
```

## Running Both Agents

Both agents run as separate systemd services on the same VM:

| Service | Port | Bot |
|---------|------|-----|
| `frepi-agent` | Telegram polling | @frepi_procurement_bot |
| `frepi-finance` | Telegram polling | @frepi_finance_bot |

They share the same Supabase database but use different Telegram bot tokens.

```bash
# Check both services
sudo systemctl status frepi-agent
sudo systemctl status frepi-finance

# Restart both
sudo systemctl restart frepi-agent frepi-finance

# Logs for both
sudo journalctl -u frepi-agent -u frepi-finance -f
```

## Database Migrations

Run migrations before first deployment:

```bash
# Local machine (with supabase CLI)
cd frepi_finance_bot
supabase link --project-ref oknotufkobuwpmtyslma
supabase db push
```

Or paste SQL files manually in the Supabase SQL Editor:
1. `migrations/001_finance_core.sql`
2. `migrations/002_menu_cmv.sql`
3. `migrations/003_watchlist_reports.sql`
4. `migrations/004_prompt_logging.sql`

## Troubleshooting

### Bot not responding

```bash
sudo systemctl status frepi-finance
sudo journalctl -u frepi-finance -n 50
```

### Token conflict

If you see "terminated by other getUpdates request":
- Stop any local development instance first
- Ensure only one process uses `TELEGRAM_FINANCE_BOT_TOKEN`

### Heartbeat not running

Check scheduler logs:
```bash
sudo journalctl -u frepi-finance | grep -i "heartbeat\|scheduler"
```

### Out of memory (running both agents)

If e2-micro can't handle both agents:
```bash
gcloud compute instances stop frepi-agent-vm --zone=southamerica-east1-c
gcloud compute instances set-machine-type frepi-agent-vm --machine-type=e2-small --zone=southamerica-east1-c
gcloud compute instances start frepi-agent-vm --zone=southamerica-east1-c
```

## Estimated Costs

Both agents on the same VM:

| Resource | Cost |
|----------|------|
| e2-small VM | ~$13/month |
| 20GB disk | ~$0.80/month |
| Network | ~$0.12/GB |
| **Total** | **~$15/month** |
