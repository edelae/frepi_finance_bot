-- ============================================================================
-- Migration 003: Price Watchlist & Monthly Financial Reports
-- Frepi Finance Agent - Supabase PostgreSQL
--
-- Creates:
--   - product_price_watchlist   : Per-product price alerts and monitoring
--   - monthly_financial_reports : Aggregated monthly financial snapshots
--
-- References existing procurement tables:
--   restaurants(id), master_list(id), suppliers(id)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- PRODUCT PRICE WATCHLIST
-- Allows restaurants to monitor specific products for price changes,
-- competitor offers, or threshold breaches. The heartbeat service checks
-- active watchlist items periodically and sends alerts via Telegram.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.product_price_watchlist (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id               INTEGER         NOT NULL REFERENCES restaurants(id),
    master_list_id              BIGINT          NOT NULL REFERENCES master_list(id),
    alert_type                  VARCHAR(50)     DEFAULT 'any_change', -- price_drop, price_increase, competitor_better, threshold
    threshold_percent           NUMERIC(5,2),
    target_price                NUMERIC(10,2),
    current_price               NUMERIC(10,2),
    current_supplier_id         INTEGER         REFERENCES suppliers(id),
    best_competitor_price       NUMERIC(10,2),
    best_competitor_supplier_id INTEGER         REFERENCES suppliers(id),
    last_alert_sent_at          TIMESTAMPTZ,
    last_checked_at             TIMESTAMPTZ,
    alert_cooldown_hours        INTEGER         DEFAULT 24,
    is_active                   BOOLEAN         DEFAULT TRUE,
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlist_restaurant
    ON public.product_price_watchlist(restaurant_id);

CREATE INDEX IF NOT EXISTS idx_watchlist_active
    ON public.product_price_watchlist(restaurant_id, master_list_id)
    WHERE is_active = TRUE;


-- ---------------------------------------------------------------------------
-- MONTHLY FINANCIAL REPORTS
-- Aggregated financial snapshot per restaurant per month.
-- Revenue is provided by the user (manual or POS integration).
-- Purchases are computed from invoices stored in the invoices table.
-- CMV = total_purchases / total_revenue * 100.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.monthly_financial_reports (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id           INTEGER         NOT NULL REFERENCES restaurants(id),
    report_month            INTEGER         NOT NULL,
    report_year             INTEGER         NOT NULL,
    -- Revenue (user input or POS integration)
    total_revenue           NUMERIC(14,2),
    revenue_source          VARCHAR(50),                             -- manual_single, manual_detailed, pos_integration
    revenue_breakdown       JSONB,                                   -- [{category, amount}]
    -- Expenses (computed from invoices)
    total_purchases         NUMERIC(14,2),
    purchase_breakdown      JSONB,                                   -- by category/supplier
    invoice_count           INTEGER,
    supplier_count          INTEGER,
    -- CMV (Custo de Mercadoria Vendida)
    cmv_percent             NUMERIC(5,2),
    cmv_target_percent      NUMERIC(5,2),
    cmv_status              VARCHAR(20),                             -- on_target, above_target, below_target, excellent, critical
    -- Cashflow
    cashflow_data           JSONB,
    -- Insights & recommendations
    insights                JSONB,
    recommended_actions     JSONB,
    savings_identified      NUMERIC(12,2),
    -- Trends
    month_over_month_change NUMERIC(6,2),
    -- Status
    status                  VARCHAR(50)     DEFAULT 'draft',         -- draft, awaiting_revenue, complete, reviewed
    generated_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW(),

    UNIQUE(restaurant_id, report_year, report_month)
);

CREATE INDEX IF NOT EXISTS idx_reports_restaurant
    ON public.monthly_financial_reports(restaurant_id);
