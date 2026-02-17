# Frepi Finance Bot

Restaurant financial intelligence agent powered by GPT-4 with function calling. Processes invoices, tracks price trends, calculates food cost (CMV) per dish, and generates monthly financial reports — all through Telegram.

Built with OpenClaw-inspired architecture (SOUL, HEARTBEAT, MEMORY patterns) adapted to Python.

## Architecture

```
User Message (Telegram)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  INTENT DETECTOR (agent/intent_detector.py)         │
│  Classifies: invoice | monthly | cmv | watchlist |  │
│              onboarding | general                   │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│  PROMPT COMPOSER (agent/prompt_composer.py)          │
│  Layer 0: SOUL (personality, always)                │
│  Layer 1: User Memory (from DB)                     │
│  Layer 2: Skill Prompt (based on intent)            │
│  Layer 3: DB Context (recent data)                  │
│  Layer 4: Conversation History                      │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│  GPT-4 + FUNCTION CALLING (23 tools)                │
│  Tools → Services → Supabase                        │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│  PROMPT LOGGER → prompt_composition_log table        │
│  Every interaction logged for feedback & iteration  │
└─────────────────────────────────────────────────────┘
```

## Features

| Feature | Description |
|---------|-------------|
| **Invoice Processing** | Upload NF photos via Telegram → GPT-4 Vision parsing → price trend analysis |
| **Monthly Closure** | Revenue input + invoice aggregation → CMV calculation → cashflow report |
| **CMV Analysis** | Menu items + ingredients → food cost % per dish → profitability tiers |
| **Price Watchlist** | Monitor products → hourly heartbeat checks → Telegram alerts |
| **Finance Onboarding** | 5-step registration: restaurant, person, role, city, savings goal |
| **Prompt Logging** | Every prompt composition logged with intent, components, timing, feedback |

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/edelae/frepi_finance_bot.git
cd frepi_finance_bot
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your keys:
#   OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY, TELEGRAM_FINANCE_BOT_TOKEN
```

### 3. Run database migrations

```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

### 4. Start the bot

```bash
frepi-finance telegram
```

### 5. Test on Telegram

Send `/start` to your bot.

## CLI Commands

```bash
frepi-finance test       # Test configuration and database connection
frepi-finance info       # Show current configuration
frepi-finance chat-cli   # Interactive chat session (terminal)
frepi-finance telegram   # Start Telegram bot (polling mode)
```

## Running Tests

```bash
pytest tests/ -v          # All 49 tests
pytest tests/ -v -k cmv   # Only CMV tests
pytest tests/ --cov       # With coverage
```

## Project Structure

```
frepi_finance/
├── soul/                      # OpenClaw-inspired personality system
│   ├── soul.py                # Base personality prompt (SOUL v1.0.0)
│   ├── identity.py            # Bot name, emoji standards, BRL formatting
│   ├── heartbeat.py           # Proactive task definitions
│   └── skills/                # Intent-specific prompt injections
│       ├── invoice_skill.py
│       ├── onboarding_skill.py
│       ├── monthly_closure_skill.py
│       ├── cmv_skill.py
│       └── watchlist_skill.py
│
├── agent/                     # Core agent logic
│   ├── finance_agent.py       # GPT-4 agent with function calling loop
│   ├── intent_detector.py     # Regex-based intent classification
│   ├── prompt_composer.py     # Layered prompt composition (4 layers)
│   └── prompt_logger.py       # Logs every composition to Supabase
│
├── memory/                    # Persistent and session state
│   ├── session_memory.py      # In-memory per-chat state
│   └── user_memory.py         # DB-backed restaurant context
│
├── tools/                     # GPT-4 function calling tools (23 total)
│   ├── onboarding_tools.py    # 3 tools: save step, complete, check user
│   ├── invoice_tools.py       # 5 tools: parse, confirm, summary, trends
│   ├── monthly_tools.py       # 4 tools: start, revenue, report, history
│   ├── cmv_tools.py           # 5 tools: add item, ingredient, calculate
│   ├── watchlist_tools.py     # 4 tools: add, remove, list, check alerts
│   └── db_tools.py            # 2 tools: search products, get suppliers
│
├── services/                  # Business logic
│   ├── invoice_parser.py      # GPT-4 Vision NF parsing
│   ├── price_trend.py         # Price trend computation and alerts
│   ├── cmv_calculator.py      # Food cost calculation engine
│   ├── cashflow.py            # Monthly cashflow report generation
│   └── heartbeat.py           # APScheduler proactive tasks
│
├── shared/                    # Infrastructure
│   ├── supabase_client.py     # DB client with Tables constants
│   └── user_identification.py # telegram_chat_id → restaurant lookup
│
├── integrations/
│   └── telegram_bot.py        # Telegram bot with photo handling
│
├── config.py                  # Environment configuration
└── main.py                    # CLI entry point
```

## Database Schema

9 new tables created in the shared Supabase instance (same DB as procurement agent):

| Table | Purpose |
|-------|---------|
| `finance_onboarding` | Registration flow state and user profile |
| `invoices` | Uploaded NFs with GPT-4 Vision parsing results |
| `invoice_line_items` | Individual products with price trend data |
| `menu_items` | Restaurant menu with sale prices and CMV metrics |
| `menu_item_ingredients` | Recipe cards linking dishes to ingredients |
| `menu_cost_history` | CMV snapshots at daily/weekly/monthly granularity |
| `product_price_watchlist` | Per-product alert configuration |
| `monthly_financial_reports` | Aggregated monthly financial snapshots |
| `prompt_composition_log` | Every LLM interaction logged for iteration |

References existing procurement tables: `restaurants`, `restaurant_people`, `suppliers`, `master_list`, `pricing_history`.

## Heartbeat (Proactive Tasks)

| Schedule | Task | Action |
|----------|------|--------|
| Every 1h (7am-10pm) | Price watchlist | Check prices, send Telegram alerts |
| Days 25-31 at 9am | Monthly reminder | Prompt users to close the month |
| Days 1-5 at 9am | Revenue request | Ask for previous month's revenue |
| Daily at 10am | CMV alert | Alert if CMV > 40% |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | GPT-4 and Vision API |
| `SUPABASE_URL` | Yes | — | Database URL |
| `SUPABASE_KEY` | Yes | — | Database anon key |
| `TELEGRAM_FINANCE_BOT_TOKEN` | Yes | — | From @BotFather |
| `CHAT_MODEL` | No | `gpt-4o` | OpenAI model |
| `ENVIRONMENT` | No | `development` | Environment name |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `CMV_TARGET_PERCENT` | No | `32.0` | Target CMV % |
| `SIGNIFICANT_PRICE_CHANGE_PERCENT` | No | `10.0` | Alert threshold |

## Prompt Engineering

Every interaction is logged to `prompt_composition_log` for monitoring and iteration. See [docs/PROMPT_ENGINEERING_GUIDE.md](docs/PROMPT_ENGINEERING_GUIDE.md) for:

- How the layered prompt system works
- Intent detection patterns and routing
- Monitoring SQL queries (correction rates, response times, tool usage)
- Step-by-step improvement playbook
- How to create new skills

## Relationship to Procurement Agent

This bot runs alongside the existing [Frepi procurement agent](https://github.com/edelae/frepi):

- **Separate Telegram bot** with its own token
- **Same Supabase database** — reads procurement tables (master_list, suppliers, pricing_history) but never writes to them
- **Shared restaurant data** — finance agent can see procurement prices for CMV calculations

## Tech Stack

| Component | Technology |
|-----------|------------|
| AI Agent | OpenAI GPT-4 with function calling |
| Vision | GPT-4 Vision for invoice parsing |
| Database | Supabase PostgreSQL |
| Messaging | Telegram Bot API (python-telegram-bot) |
| Scheduler | APScheduler (asyncio) |
| CLI | Click + Rich |
| Language | Python 3.10+ |
