-- ============================================================================
-- Migration 004: Prompt Composition Logging
-- Frepi Finance Agent - Supabase PostgreSQL
--
-- Creates:
--   - prompt_composition_log : Tracks every LLM call for debugging,
--                              performance monitoring, and prompt iteration
--
-- References existing procurement tables:
--   restaurants(id)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- PROMPT COMPOSITION LOG
-- Records every agent interaction: what the user said, which intent was
-- detected, how the prompt was composed, what tools were called, and
-- whether the user provided feedback or corrections.
-- Used for:
--   - Debugging incorrect agent responses
--   - Measuring intent detection accuracy
--   - Tracking prompt version effectiveness
--   - Identifying correction patterns to improve prompts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prompt_composition_log (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id               INTEGER         REFERENCES restaurants(id),
    telegram_chat_id            BIGINT,
    session_id                  VARCHAR(100),
    -- Input
    user_message                TEXT            NOT NULL,
    detected_intent             VARCHAR(50),
    intent_confidence           NUMERIC(3,2),
    -- Composition
    base_prompt_version         VARCHAR(20),
    injected_components         JSONB,                               -- [{name, type, token_count}]
    context_items_count         INTEGER,
    final_prompt_token_estimate INTEGER,
    -- Execution
    model_used                  VARCHAR(50),
    execution_time_ms           INTEGER,
    tool_calls_made             JSONB,                               -- [{tool_name, args_summary}]
    error_occurred              BOOLEAN         DEFAULT FALSE,
    error_message               TEXT,
    -- Response & feedback
    response_length             INTEGER,
    user_feedback               VARCHAR(20),                         -- positive, negative, correction
    correction_details          TEXT,
    created_at                  TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_log_restaurant
    ON public.prompt_composition_log(restaurant_id);

CREATE INDEX IF NOT EXISTS idx_prompt_log_intent
    ON public.prompt_composition_log(detected_intent);

CREATE INDEX IF NOT EXISTS idx_prompt_log_feedback
    ON public.prompt_composition_log(user_feedback)
    WHERE user_feedback IS NOT NULL;
