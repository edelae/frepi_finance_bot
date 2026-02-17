# Prompt Engineering & Monitoring Guide
## Frepi Finance Agent - Agent SDK Design Patterns

This guide teaches you how to monitor, debug, and iteratively improve the prompt system
that powers the Frepi Finance Agent. It covers the architecture, logging, feedback loops,
and practical workflows for making the agent smarter over time.

---

## 0. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        USER MESSAGE (Telegram)                        │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    INTENT DETECTOR                                    │
│                 (agent/intent_detector.py)                            │
│                                                                      │
│  Input:  user_message, has_photo, is_new_user                        │
│  Output: DetectedIntent(intent, confidence, trigger_pattern)         │
│                                                                      │
│  LOGGED: intent + confidence + trigger_pattern                       │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    PROMPT COMPOSER                                    │
│                 (agent/prompt_composer.py)                            │
│                                                                      │
│  Layer 0: SOUL.py ─────────────── ALWAYS injected                    │
│  Layer 1: User Memory ─────────── FROM finance_onboarding DB         │
│  Layer 2: Skill Prompt ────────── BASED ON detected intent           │
│  Layer 3: DB Context ──────────── RECENT data (invoices, watchlist)  │
│  Layer 4: Conversation ────────── MANAGED by OpenAI messages array   │
│                                                                      │
│  LOGGED: each component name, layer, token_estimate, final hash      │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    GPT-4 + FUNCTION CALLING                          │
│                 (agent/finance_agent.py)                              │
│                                                                      │
│  Tool calls → tools/*.py → services/*.py → Supabase                 │
│                                                                      │
│  LOGGED: tool_calls_made[], execution_time_ms, response_length       │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    PROMPT LOGGER                                     │
│                 (agent/prompt_logger.py)                              │
│                                                                      │
│  Writes EVERYTHING to prompt_composition_log table                   │
│  Later: user_feedback + correction_details added                     │
└──────────────────────────────────────────────────────────────────────┘
```

**Key principle**: Every prompt injection is traced. You can reconstruct exactly what
the agent "saw" for any interaction by reading the `prompt_composition_log` table.

---

## 1. Prompt Composition Layers

Every user message goes through a layered composition pipeline:

```
Layer 0: SOUL (soul/soul.py)
    → Always present. Defines personality, domain knowledge, formatting rules.
    → Version tracked in prompt_composer.py as SOUL_PROMPT_VERSION.

Layer 1: User Memory (memory/user_memory.py)
    → Loaded from DB when restaurant_id is known.
    → Contains: restaurant name, city, invoice count, CMV, savings goals.

Layer 2: Skill Prompt (soul/skills/*.py)
    → Injected based on detected intent.
    → Provides task-specific instructions, formats, and tool usage guides.

Layer 3: DB Context (dynamic)
    → Recent invoices, current watchlist, latest report.
    → Pulled at query time, not cached.

Layer 4: Conversation History
    → Managed by OpenAI messages array.
    → Includes tool calls and results.
```

## 2. Intent Detection

The intent detector (`agent/intent_detector.py`) uses keyword pattern matching:

| Intent | Triggers | Skill File |
|--------|----------|------------|
| `invoice_upload` | Photo, "NF", "nota fiscal", menu option 1 | `invoice_skill.py` |
| `monthly_closure` | "fechamento", "relatório", menu option 2 | `monthly_closure_skill.py` |
| `cmv_query` | "CMV", "cardápio", "prato", menu option 3 | `cmv_skill.py` |
| `watchlist` | "acompanhar", "monitorar", menu option 4 | `watchlist_skill.py` |
| `onboarding` | New user (no DB record) | `onboarding_skill.py` |
| `general` | No pattern match | None (SOUL only) |

## 3. Logging & Tracing

Every interaction logs to `prompt_composition_log`:

| Field | Description |
|-------|-------------|
| `user_message` | Original user input |
| `detected_intent` | Which intent was detected |
| `intent_confidence` | 0-1 confidence score |
| `injected_components` | Array of `{name, type, token_count}` |
| `execution_time_ms` | Total processing time |
| `tool_calls_made` | Array of `{tool_name, args_summary}` |
| `user_feedback` | `positive`, `negative`, or `correction` |

## 4. Feedback Loop

### Implicit Signals
- **Corrections**: User says "não, o preço era R$ 42" → `user_feedback = 'correction'`
- **Repeated questions**: Same intent within 2 messages → possible misunderstanding
- **Abandonment**: User sends /start mid-flow → flow wasn't helpful

### Explicit Signals
- After invoice confirmation: "Os dados estão corretos?" → YES/NO
- After report generation: "O relatório ficou bom?" (future)

### Weekly Review Process
1. Query correction rate by intent (see SQL below)
2. Review top 5 corrected interactions
3. Identify pattern in corrections
4. Update relevant skill prompt
5. Bump SOUL_PROMPT_VERSION
6. Compare before/after metrics next week

## 5. Prompt Versioning

- Version format: `MAJOR.MINOR.PATCH`
- Stored in `prompt_composer.py` as `SOUL_PROMPT_VERSION`
- Every log entry records the version used
- Compare effectiveness between versions with SQL queries

## 6. Monitoring Queries

### Correction Rate by Intent
```sql
SELECT detected_intent,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE user_feedback = 'correction') as corrections,
    ROUND(
        COUNT(*) FILTER (WHERE user_feedback = 'correction')::NUMERIC /
        NULLIF(COUNT(*), 0) * 100, 1
    ) as correction_rate_pct
FROM prompt_composition_log
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY detected_intent
ORDER BY correction_rate_pct DESC;
```

### Average Response Time by Intent
```sql
SELECT detected_intent,
    ROUND(AVG(execution_time_ms)) as avg_ms,
    MAX(execution_time_ms) as max_ms,
    COUNT(*) as total
FROM prompt_composition_log
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY detected_intent
ORDER BY avg_ms DESC;
```

### Prompt Version Effectiveness
```sql
SELECT base_prompt_version,
    COUNT(*) as total_interactions,
    COUNT(*) FILTER (WHERE user_feedback = 'positive') as positive,
    COUNT(*) FILTER (WHERE user_feedback = 'negative') as negative,
    COUNT(*) FILTER (WHERE user_feedback = 'correction') as corrections,
    COUNT(*) FILTER (WHERE error_occurred) as errors,
    ROUND(AVG(execution_time_ms)) as avg_response_ms
FROM prompt_composition_log
GROUP BY base_prompt_version
ORDER BY base_prompt_version DESC;
```

### Most Common Intents
```sql
SELECT detected_intent,
    COUNT(*) as count,
    ROUND(COUNT(*)::NUMERIC / SUM(COUNT(*)) OVER () * 100, 1) as pct
FROM prompt_composition_log
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY detected_intent
ORDER BY count DESC;
```

### Tool Usage Frequency
```sql
SELECT
    tool_call->>'tool_name' as tool_name,
    COUNT(*) as usage_count
FROM prompt_composition_log,
    jsonb_array_elements(tool_calls_made) as tool_call
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY tool_call->>'tool_name'
ORDER BY usage_count DESC;
```

## 7. Iteration Playbook

### Step-by-step improvement cycle:

1. **Identify**: Query correction rates → find weakest intent
2. **Investigate**: Read actual corrected messages from logs
3. **Hypothesize**: What pattern of user input leads to wrong behavior?
4. **Update**: Modify the relevant skill prompt in `soul/skills/`
5. **Version**: Bump `SOUL_PROMPT_VERSION`
6. **Deploy**: Push update and restart bot
7. **Measure**: After 1 week, compare correction rates between versions
8. **Document**: Record what worked/didn't in this file

---

## 8. Practical Log Monitoring

### Reading logs in real-time (during development)

The agent logs every prompt injection to stdout. When running the bot locally:

```bash
# Start the bot with verbose logging
LOG_LEVEL=DEBUG frepi-finance telegram 2>&1 | tee /tmp/frepi-finance.log

# In another terminal, watch for prompt compositions
tail -f /tmp/frepi-finance.log | grep "PROMPT COMPOSED"

# Watch for intent detections
tail -f /tmp/frepi-finance.log | grep "INTENT:"

# Watch for tool calls
tail -f /tmp/frepi-finance.log | grep "TOOL CALL:"
```

### Log output format

Each interaction produces 3 key log lines:

```
🎯 INTENT: invoice_upload (confidence=0.95, pattern=photo)
📝 PROMPT COMPOSED: intent=invoice_upload, components=[soul(450t), user_memory(80t), skill_invoice_upload(620t), db_context(150t)], total_tokens≈1300, hash=a1b2c3d4
✅ RESPONSE: 847 chars, 2340ms, 2 tool calls
```

This tells you:
- **What the agent understood** (intent + confidence)
- **What was injected** (which layers, how many tokens each)
- **What happened** (response size, time, tool calls)

### Querying the database for historical analysis

```bash
# Connect to Supabase SQL editor or use psql:

# Last 10 interactions for a specific restaurant
SELECT user_message, detected_intent, intent_confidence,
       injected_components, execution_time_ms, user_feedback
FROM prompt_composition_log
WHERE restaurant_id = YOUR_RESTAURANT_ID
ORDER BY created_at DESC
LIMIT 10;

# Find all corrections (the gold mine for improvement)
SELECT user_message, detected_intent, correction_details, created_at
FROM prompt_composition_log
WHERE user_feedback = 'correction'
ORDER BY created_at DESC;
```

---

## 9. Creating New Skills

When you need a new capability (e.g., "POS Integration"):

### Step 1: Create the skill prompt file
```python
# soul/skills/pos_skill.py
POS_SKILL_PROMPT = """
## Habilidade Ativa: Integração POS

[Instructions for the agent when POS-related intent is detected]
""".strip()
```

### Step 2: Register in soul/skills/__init__.py
```python
from .pos_skill import POS_SKILL_PROMPT

SKILL_PROMPTS = {
    # ... existing skills ...
    "pos_integration": POS_SKILL_PROMPT,
}
```

### Step 3: Add intent patterns
```python
# agent/intent_detector.py
INTENT_PATTERNS["pos_integration"] = {
    "keywords": [r"\bpos\b", r"\bcaixa\b", r"\bpdv\b"],
    "phrases": [r"integrar\s+pos", r"conectar\s+caixa"],
    "confidence_keyword": 0.82,
    "confidence_phrase": 0.90,
}
```

### Step 4: Add tools (if needed)
```python
# tools/pos_tools.py
POS_TOOLS = [...]
```

### Step 5: Bump version
```python
# soul/soul.py
SOUL_VERSION = "1.1.0"  # Minor version for new skill
```

---

## 10. Agent SDK Design Patterns

### Pattern 1: Layered Prompt Injection
Instead of one monolithic system prompt, compose from discrete layers.
Each layer is independently versionable and testable.

**Why**: A single large prompt becomes unmaintainable. Layers let you
change one skill without affecting others.

### Pattern 2: Intent-First Routing
Detect intent BEFORE composing the prompt. Only inject the relevant
skill instructions.

**Why**: Smaller prompts = faster responses + less confusion for the model.
A 1500-token focused prompt beats a 5000-token kitchen-sink prompt.

### Pattern 3: Source-of-Truth Logging
Log the COMPOSITION, not the raw prompt text. Store which components
were injected, not the full prompt string.

**Why**: Prompts are large and change often. Logging component names + versions
is compact and lets you reconstruct any prompt from source code + version.

### Pattern 4: Implicit Feedback Detection
Don't just ask "was this helpful?" - detect corrections from conversation flow.
"Não" after a confirmation = negative feedback. Re-sending the same photo =
the first parse failed.

**Why**: Users don't answer surveys. But they DO correct the agent. Capture that.

### Pattern 5: Heartbeat for Proactive Value
Schedule periodic checks that send messages ONLY when meaningful.
Never send empty heartbeats.

**Why**: Proactive alerts (price dropped, month-end reminder) make the agent
feel alive and valuable, not just reactive.

### Pattern 6: Shared Database, Separate Agents
The finance agent reads from procurement tables but never writes to them.
Each agent owns its own tables.

**Why**: Prevents data corruption while enabling cross-agent intelligence.
The finance agent can see procurement prices; the procurement agent can
see invoice-validated costs.

---

## 11. Debugging Checklist

When the agent gives a wrong or unexpected response:

1. **Check intent**: Was the intent detected correctly?
   ```sql
   SELECT detected_intent, intent_confidence, user_message
   FROM prompt_composition_log WHERE id = 'LOG_ID';
   ```

2. **Check components**: Were the right skill prompts injected?
   ```sql
   SELECT injected_components FROM prompt_composition_log WHERE id = 'LOG_ID';
   ```

3. **Check tools**: Did the right tools get called?
   ```sql
   SELECT tool_calls_made FROM prompt_composition_log WHERE id = 'LOG_ID';
   ```

4. **Check data**: Did the DB return the expected data?
   - Read the tool call results in conversation history
   - Check if the data in Supabase matches expectations

5. **Check prompt**: Reconstruct the full prompt
   - Read `soul/soul.py` at the logged `base_prompt_version`
   - Add the skill prompt from the logged intent
   - Add the user memory and DB context

6. **Fix**: Update the relevant layer and test again

---

## 12. Metrics Dashboard (Future)

Build a simple dashboard querying `prompt_composition_log`:

| Metric | Query | Target |
|--------|-------|--------|
| Daily active users | DISTINCT telegram_chat_id | Growing |
| Avg response time | AVG(execution_time_ms) | < 3000ms |
| Correction rate | corrections / total | < 10% |
| Intent distribution | GROUP BY detected_intent | Balanced |
| Tool failure rate | error_occurred = true | < 5% |
| Feedback coverage | user_feedback IS NOT NULL / total | > 30% |
