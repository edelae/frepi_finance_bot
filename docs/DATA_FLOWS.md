# Data Flow Registry — Frepi Finance Agent

This document maps every data movement in the finance agent: what triggers it, where data comes from, what transforms it, where it lands, and what preferences influence the outcome.

---

## Table of Contents

1. [Message Pipeline & Intent Detection](#1-message-pipeline--intent-detection)
2. [5-Layer Prompt Composition](#2-5-layer-prompt-composition)
3. [Onboarding Flow](#3-onboarding-flow)
4. [Invoice Processing Pipeline](#4-invoice-processing-pipeline)
5. [Price Trend Computation](#5-price-trend-computation)
6. [Monthly Closure & Reporting](#6-monthly-closure--reporting)
7. [CMV / Food Cost Calculation](#7-cmv--food-cost-calculation)
8. [Price Watchlist & Alerts](#8-price-watchlist--alerts)
9. [Heartbeat (Scheduled Jobs)](#9-heartbeat-scheduled-jobs)
10. [Preference Learning (Shared with Procurement)](#10-preference-learning-shared-with-procurement)
11. [Table Read/Write Summary](#11-table-readwrite-summary)
12. [Cross-Agent Data Dependencies](#12-cross-agent-data-dependencies)
13. [Thresholds & Constants](#13-thresholds--constants)

---

## 1. Message Pipeline & Intent Detection

```
Flow ID:       FIN-001
Trigger:        User sends any Telegram message
Source:         Telegram Bot API (polling)
Transform:      telegram_bot.py → finance_agent.py → intent_detector.py
Destination:    GPT-4 call with composed prompt + tools
Conditions:     Always runs
Preferences:    Intent determines which skill prompt is loaded
```

**Step-by-step pipeline:**

| Step | Action | Component |
|------|--------|-----------|
| 1 | Receive message | `handle_message()` in telegram_bot.py |
| 2 | Get/create session | In-memory `SessionMemory` per chat_id |
| 3 | Detect intent | `detect_intent()` in intent_detector.py |
| 4 | Load user memory | DB read from `finance_onboarding` + `restaurants` |
| 5 | Build DB context | Recent invoices, watchlist count, monthly report status |
| 6 | Build drip context | Preference questions from `preference_collection_queue` |
| 7 | Compose 5-layer prompt | `prompt_composer.py` |
| 8 | Log prompt | INSERT `prompt_composition_log` |
| 9 | Call GPT-4 | OpenAI API with 27 tools |
| 10 | Execute tool calls | Loop until GPT-4 stops calling tools |
| 11 | Log results | UPDATE `prompt_composition_log` |
| 12 | Send response | Telegram reply (split if >4096 chars) |

### User Identification (on /start or first message)

| Query | Table | Filter | Returns |
|-------|-------|--------|---------|
| Completed finance user | `finance_onboarding` | `telegram_chat_id`, `status = "completed"` | restaurant_id, names |
| In-progress onboarding | `finance_onboarding` | `telegram_chat_id`, `status = "in_progress"` | Partial data |
| Procurement account | `restaurant_people` | `whatsapp_number = chat_id_str` | restaurant_id, person_id |

### Intent Detection (regex-based)

| Intent | Trigger Patterns | Confidence | Menu Key |
|--------|-----------------|------------|----------|
| `onboarding` | `is_new_user = True` | 1.0 | — |
| `invoice_upload` | `has_photo`, "nf", "nota fiscal", "cupom" | 0.85–0.95 | 1 |
| `monthly_closure` | "fechamento", "faturamento", "resultado", "relatório" | 0.82–0.90 | 2 |
| `cmv_query` | "cmv", "cardápio", "ficha técnica", "custo" | 0.80–0.90 | 3 |
| `watchlist` | "acompanhar", "monitorar", "alerta", "preço" | 0.82–0.90 | 4 |
| `general` | No pattern match | 0.50 | — |

---

## 2. 5-Layer Prompt Composition

```
Flow ID:       FIN-002
Trigger:        Every message processed by the agent
Source:         SOUL constant + DB queries + intent detection
Transform:      prompt_composer.py
Destination:    GPT-4 system message
Conditions:     Always runs; layers conditionally included
Preferences:    User memory personalizes; skill prompt shapes behavior
```

| Layer | Name | Source | Condition | Purpose |
|-------|------|--------|-----------|---------|
| 0 | SOUL | `soul/soul.py` (constant) | Always | Base personality, rules, tone |
| 1 | User Memory | `finance_onboarding` + `restaurants` + `monthly_financial_reports` | restaurant_id exists | Personalization, CMV targets |
| 2 | Skill Prompt | `soul/skills/{intent}_skill.py` | Intent detected | Task-specific behavior |
| 3 | DB Context | Recent invoices, watchlist status, latest report | Data available | Current state awareness |
| 4 | Drip Context | `preference_collection_queue` | Not onboarding, restaurant linked | Progressive preference collection |

**Token budget:** Max 4000 tokens. If exceeded, layers shed in reverse priority (Drip → DB Context → Skill).

**Logging:** Every composition is written to `prompt_composition_log` with: components list, token estimate, prompt hash, detected intent, confidence.

---

## 3. Onboarding Flow

```
Flow ID:       FIN-003
Trigger:        New user detected (not in finance_onboarding)
Source:         User responses via Telegram
Transform:      onboarding_tools.py (3 tools)
Destination:    finance_onboarding table
Conditions:     is_new_user = True
Preferences:    Engagement choice determines future drip frequency
```

### 5-step registration:

| Step | Field | GPT-4 Tool Call | Writes To |
|------|-------|-----------------|-----------|
| 1 | restaurant_name | `save_onboarding_step("restaurant_name", value)` | `finance_onboarding` |
| 2 | person_name | `save_onboarding_step("person_name", value)` | `finance_onboarding` |
| 3 | is_owner / relationship | `save_onboarding_step("is_owner", value)` | `finance_onboarding` |
| 4 | city + state | `save_onboarding_step("city", value)` | `finance_onboarding` |
| 5 | savings_opportunity | `save_onboarding_step("savings_opportunity", value)` | `finance_onboarding` |

**Phase progression:** Each step updates `current_phase` to the next field name.

### Completion:

| Step | Action | Writes To |
|------|--------|-----------|
| 6 | `complete_onboarding()` | `finance_onboarding` (status = "completed", completed_at = NOW()) |
| 7 | Engagement choice | `finance_onboarding` (engagement_choice), `engagement_profile` (UPSERT) |

**Cross-check tool:** `check_existing_user()` queries `restaurant_people` to detect if user already has a procurement account, enabling data reuse.

---

## 4. Invoice Processing Pipeline

```
Flow ID:       FIN-004
Trigger:        User uploads photo(s) + types "pronto", or GPT-4 calls parse_invoice_photo
Source:         Telegram photo → GPT-4 Vision
Transform:      invoice_tools.py → invoice_parser.py → price_trend.py
Destination:    invoices, invoice_line_items
Conditions:     Restaurant must be onboarded
Preferences:    None (raw extraction)
```

### 4a. Single Invoice Parse

| Step | Action | API/Table | Writes To |
|------|--------|-----------|-----------|
| 1 | Download image | HTTP GET from Telegram → base64 | In-memory |
| 2 | GPT-4 Vision extraction | OpenAI `gpt-4o` (temp=0.1, max_tokens=4096) | In-memory ParsedInvoice |
| 3 | Insert invoice record | — | `invoices` (status = "parsed") |
| 4 | Insert line items | For each extracted item | `invoice_line_items` |
| 5 | Compute price trends | FIN-005 | `invoice_line_items` (UPDATE trend fields) |

**Fields extracted by Vision:** supplier_name, supplier_cnpj, invoice_date, invoice_number, items[] (product_name, quantity, unit, unit_price, total_price), total_amount, confidence_score.

**Data preserved:** `raw_extraction_result` (full JSON) stored on `invoices` for audit.

### 4b. Batch Parse (multiple photos)

Same as 4a repeated for each photo URL. Triggered when user sends multiple photos then "pronto".

### 4c. Invoice Confirmation

```
Flow ID:       FIN-004c
Trigger:        GPT-4 calls confirm_invoice(invoice_id)
Writes:         invoices SET status = "confirmed", user_confirmed = True
```

---

## 5. Price Trend Computation

```
Flow ID:       FIN-005
Trigger:        After every invoice parse (automatic)
Source:         invoice_line_items (current + historical)
Transform:      price_trend.py → compute_trends_for_invoice()
Destination:    invoice_line_items (trend columns updated)
Conditions:     Invoice must have line items
Preferences:    Significant change threshold = 10%
```

| Step | Action | Reads | Writes |
|------|--------|-------|--------|
| 1 | Get current line items | `invoice_line_items` WHERE invoice_id | — |
| 2 | For each item: find previous price | `invoice_line_items` WHERE same product, different invoice, ORDER BY created_at DESC | — |
| 3 | Calculate change % | `((current - previous) / previous) * 100` | — |
| 4 | Update trend fields | — | `invoice_line_items` SET previous_price, price_change_percent, price_trend, is_significant_change |

**Trend values:** "up", "down", "stable", "new" (no prior data).

**Significant change flag:** Set when |change%| >= 10%.

---

## 6. Monthly Closure & Reporting

```
Flow ID:       FIN-006
Trigger:        User selects menu option 2 or says "fechamento"
Source:         invoices (purchases) + user input (revenue)
Transform:      monthly_tools.py → cashflow.py
Destination:    monthly_financial_reports
Conditions:     Restaurant must be onboarded
Preferences:    cmv_target_percent from finance_onboarding (default 32%)
```

### 3-step process:

### 6a. Start Closure

| Step | Action | Reads | Writes |
|------|--------|-------|--------|
| 1 | Determine month | Current date logic (day <= 10 → previous month) | — |
| 2 | Check existing report | `monthly_financial_reports` WHERE restaurant_id + year + month | — |
| 3 | Pre-calculate purchases | `invoices` WHERE date range → SUM(total_amount) | — |
| 4 | Create report (if new) | — | INSERT `monthly_financial_reports` (status = "awaiting_revenue") |

### 6b. Submit Revenue

| Step | Action | Writes |
|------|--------|--------|
| 1 | User provides total_revenue | UPDATE `monthly_financial_reports` SET total_revenue, revenue_source, status = "complete" |

### 6c. Generate Full Report

| Step | Action | Reads | Writes |
|------|--------|-------|--------|
| 1 | Get report + revenue | `monthly_financial_reports` | — |
| 2 | Calculate purchases | `invoices` WHERE month → SUM, GROUP BY supplier | — |
| 3 | Compute CMV | purchases / revenue * 100 | — |
| 4 | Compare previous month | `monthly_financial_reports` (previous) | — |
| 5 | Generate insights | Top suppliers, CMV status, MoM change | — |
| 6 | Save complete report | — | UPDATE `monthly_financial_reports` SET all computed fields + generated_at |

**CMV status classification:**

| CMV % | Status |
|-------|--------|
| <= target | on_target |
| <= 40% | above_target |
| > 40% | critical |

---

## 7. CMV / Food Cost Calculation

```
Flow ID:       FIN-007
Trigger:        User asks about food cost or selects menu option 3
Source:         menu_items + menu_item_ingredients + invoice_line_items + pricing_history
Transform:      cmv_tools.py → cmv_calculator.py
Destination:    menu_items, menu_item_ingredients (cost fields)
Conditions:     Menu items must exist
Preferences:    None (pure cost calculation)
```

### 7a. Add Menu Item

```
Trigger:    GPT-4 calls add_menu_item(name, price, category)
Writes:     INSERT menu_items (restaurant_id, item_name, sale_price, category)
```

### 7b. Add Ingredient

```
Trigger:    GPT-4 calls add_ingredient(menu_item_id, name, qty, unit, waste%)
Writes:     INSERT menu_item_ingredients
```

### 7c. Calculate Food Cost

| Step | Action | Reads | Writes |
|------|--------|-------|--------|
| 1 | Get menu item | `menu_items` WHERE id | — |
| 2 | Get ingredients | `menu_item_ingredients` WHERE menu_item_id | — |
| 3 | For each ingredient: find cost | Priority: `invoice_line_items` (by master_list_id) → `invoice_line_items` (by name) → `pricing_history` | — |
| 4 | Calculate cost per serving | qty * unit_cost * (1 + waste%/100) | UPDATE `menu_item_ingredients` SET cost fields |
| 5 | Aggregate total cost | SUM(adjusted costs) | — |
| 6 | Compute metrics | food_cost%, contribution_margin, profitability_tier | UPDATE `menu_items` SET cost metrics |

**Profitability tiers:**

| Food Cost % | Tier |
|------------|------|
| > 40% | negative |
| > 35% | low |
| > 28% | medium |
| <= 28% | high |

### 7d. Get Unprofitable Items

```
Trigger:    GPT-4 calls get_unprofitable_items(threshold=35)
Reads:      menu_items WHERE food_cost_percent > threshold
Returns:    List of dishes above threshold
```

---

## 8. Price Watchlist & Alerts

```
Flow ID:       FIN-008
Trigger:        User asks to monitor a product, or heartbeat runs check
Source:         master_list + pricing_history + invoice_line_items
Transform:      watchlist_tools.py
Destination:    product_price_watchlist + Telegram alerts
Conditions:     Product must exist in master_list
Preferences:    Alert type and thresholds are user-configured
```

### 8a. Add to Watchlist

| Step | Reads | Writes |
|------|-------|--------|
| 1 | Search product | `master_list` WHERE product_name ILIKE | — |
| 2 | Create watchlist entry | — | INSERT `product_price_watchlist` (alert_type, threshold, target_price) |

### 8b. Check Alerts (manual or heartbeat)

| Step | Action | Reads | Writes |
|------|--------|-------|--------|
| 1 | Get active watchlist | `product_price_watchlist` WHERE is_active | — |
| 2 | For each: check cooldown | last_alert_sent_at + cooldown_hours | — |
| 3 | Get current price | `pricing_history` (priority 1) → `invoice_line_items` (priority 2) | — |
| 4 | Compare vs stored price | Calculate change% | — |
| 5 | Evaluate alert condition | Match alert_type rules | — |
| 6 | If triggered: update + alert | — | UPDATE `product_price_watchlist` (current_price, last_alert_sent_at) |

**Alert types:**

| Type | Condition |
|------|-----------|
| any_change | \|change%\| >= threshold |
| price_drop | change% <= -threshold |
| price_increase | change% >= threshold |
| threshold | new_price >= target_price |

---

## 9. Heartbeat (Scheduled Jobs)

```
Flow ID:       FIN-009
Trigger:        APScheduler cron jobs (4 schedules)
Source:         Database tables
Transform:      heartbeat.py
Destination:    Telegram messages (proactive alerts)
Conditions:     Business hours, date ranges, CMV thresholds
Preferences:    Per-restaurant CMV targets
```

### Job 1: Price Watchlist Check

```
Schedule:   Every 1 hour, 7am–10pm BRT
Reads:      product_price_watchlist, pricing_history, invoice_line_items, finance_onboarding
Writes:     product_price_watchlist (UPDATE current_price, timestamps)
Output:     Telegram alert: "🔔 Alerta de Preço: {product} {direction} {change%}"
```

### Job 2: Monthly Closure Reminder

```
Schedule:   Days 25–31, 9am BRT
Reads:      finance_onboarding (completed), monthly_financial_reports
Writes:     None
Output:     Telegram: "📅 Lembrete: Faltam poucos dias para fechar o mês!"
Condition:  Only if no report exists for current month
```

### Job 3: Revenue Request

```
Schedule:   Days 1–5, 9am BRT
Reads:      finance_onboarding (completed), monthly_financial_reports
Writes:     None
Output:     Telegram: "📊 Faturamento de {month}: Qual foi o total?"
Condition:  Only if previous month report missing or no revenue submitted
```

### Job 4: CMV Alert

```
Schedule:   Daily at 10am BRT
Reads:      monthly_financial_reports (latest per restaurant), finance_onboarding
Writes:     None
Output:     Telegram: "⚠️ Alerta de CMV: {cmv}% — acima da meta"
Condition:  Only if cmv_percent > 40%
```

---

## 10. Preference Learning (Shared with Procurement)

```
Flow ID:       FIN-010
Trigger:        Drip questions, onboarding, corrections
Source:         User responses
Transform:      preference_tools.py → engagement_scoring.py
Destination:    restaurant_product_preferences, preference_corrections, engagement_profile
Conditions:     Restaurant must be linked
Preferences:    Same system as procurement agent (shared tables)
```

The finance agent shares the preference/engagement system with the procurement agent. See `frepi-agent/docs/DATA_FLOWS.md` sections 7–9 for the complete preference lifecycle.

**Finance-specific preference tools:**

| Tool | Action | Writes To |
|------|--------|-----------|
| `save_engagement_choice_finance` | Set onboarding depth (Top 5/10/Skip) | `finance_onboarding`, `engagement_profile` |
| `save_product_preference_finance` | Save brand/price/quality preference | `restaurant_product_preferences`, `preference_collection_queue` |
| `answer_drip_question` | Record drip response | `engagement_profile`, `restaurant_product_preferences`, `preference_collection_queue` |
| `save_preference_correction` | Log and apply correction | `preference_corrections`, `restaurant_product_preferences`, `engagement_profile` |

---

## 11. Table Read/Write Summary

### Finance-Specific Tables (9)

| Table | Read By | Written By |
|-------|---------|------------|
| `finance_onboarding` | User identification, user memory, heartbeat, onboarding tools | `save_onboarding_step`, `complete_onboarding`, `save_engagement_choice` |
| `invoices` | DB context, monthly tools, cashflow, trend computation, heartbeat | `parse_invoice_photo` (INSERT), `confirm_invoice` (UPDATE) |
| `invoice_line_items` | Trend computation, CMV calculator, watchlist alerts, price trends | `parse_invoice_photo` (INSERT), `compute_trends` (UPDATE) |
| `menu_items` | CMV tools, unprofitable query | `add_menu_item` (INSERT), `calculate_food_cost` (UPDATE) |
| `menu_item_ingredients` | CMV calculator | `add_ingredient` (INSERT), `calculate_food_cost` (UPDATE costs) |
| `menu_cost_history` | CMV history query | CMV snapshot jobs (INSERT) |
| `product_price_watchlist` | Watchlist tools, heartbeat | `add_to_watchlist` (INSERT), `check_alerts` (UPDATE), `remove` (soft delete) |
| `monthly_financial_reports` | User memory, DB context, heartbeat, report tools | `start_closure` (INSERT), `submit_revenue` (UPDATE), `generate_report` (UPDATE) |
| `prompt_composition_log` | — (audit only) | Every agent call (INSERT + UPDATE) |

### Shared Tables (Read-Only from Finance)

| Table | Read By | Written By (Finance) |
|-------|---------|---------------------|
| `master_list` | Product search (db_tools), watchlist lookup, ingredient cost lookup | Never |
| `suppliers` | — | Never |
| `restaurants` | User memory (quality_requirements, price_sensitivity) | Never |
| `restaurant_people` | User identification (onboarding cross-check) | Never |
| `pricing_history` | Ingredient cost lookup (fallback), watchlist price check | Never |

### Shared Preference Tables (Read-Write)

| Table | Read By | Written By |
|-------|---------|------------|
| `restaurant_product_preferences` | Drip question selection | `save_product_preference`, `answer_drip_question`, `save_preference_correction` |
| `preference_collection_queue` | Drip question selection | `save_product_preference` (mark collected), `answer_drip_question` (mark answered/skipped) |
| `engagement_profile` | Drip question count, prompt layer 4 | `save_engagement_choice`, `answer_drip_question`, `save_preference_correction` |
| `preference_corrections` | — (audit) | `save_preference_correction` |

---

## 12. Cross-Agent Data Dependencies

The finance agent **reads from** procurement tables but **never writes to them**. Data flows between agents:

```
PROCUREMENT → FINANCE (read-only)
├── master_list           → Product names for watchlist, ingredient matching
├── suppliers             → Supplier names for context
├── restaurants           → Quality requirements, price sensitivity
├── restaurant_people     → User identification cross-check
├── pricing_history       → Ingredient costs (fallback), watchlist comparison
└── purchase_orders       → (Future) order analysis

FINANCE → PROCUREMENT (via shared tables)
├── engagement_profile         → Both agents use engagement score
├── preference_collection_queue → Both agents can mark preferences collected
├── restaurant_product_preferences → Both agents can write preferences
└── preference_corrections     → Both agents log corrections
```

**Key rule:** Finance agent discovers costs primarily from its own `invoice_line_items`, falling back to procurement's `pricing_history` only when invoice data is unavailable.

---

## 13. Thresholds & Constants

| Constant | Value | Used In |
|----------|-------|---------|
| Price change significant | >= 10% | Price trend computation (FIN-005) |
| Watchlist cooldown | 24 hours | Alert check (FIN-008b) |
| CMV critical | > 40% | Monthly report (FIN-006c), Heartbeat (FIN-009 Job 4) |
| CMV above target | 35–40% | Monthly report classification |
| CMV default target | 32% | User memory (overrideable per restaurant) |
| Food cost unprofitable | > 35% | CMV query (FIN-007d) |
| Food cost negative | > 40% | Profitability tier |
| Invoice parse confidence | >= 0.8 | Item preservation threshold |
| Prompt token budget | 4000 | Prompt composition (FIN-002) |
| Telegram message max | 4096 chars | Response splitting |
| Heartbeat business hours | 7am–10pm BRT | Watchlist check (FIN-009 Job 1) |
| Monthly reminder window | Days 25–31 | Heartbeat (FIN-009 Job 2) |
| Revenue request window | Days 1–5 | Heartbeat (FIN-009 Job 3) |
| Engagement: high | score >= 0.65 | Drip 2 questions/session |
| Engagement: medium | score >= 0.35 | Drip 1 question/session |
| Engagement: low | score >= 0.10 | Drip 0 questions/session |
| Engagement: dormant | score < 0.10 | No drip, no proactive questions |
