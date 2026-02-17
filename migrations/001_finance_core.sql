-- ============================================================================
-- Migration 001: Finance Core Tables
-- Frepi Finance Agent - Supabase PostgreSQL
--
-- Creates:
--   - finance_onboarding  : Tracks onboarding sessions for new finance users
--   - invoices            : Nota Fiscal storage and parsing results
--   - invoice_line_items  : Individual products extracted from invoices
--
-- References existing procurement tables:
--   restaurants(id), restaurant_people(id), suppliers(id),
--   master_list(id), purchase_orders(order_id)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- FINANCE ONBOARDING
-- Captures the progressive onboarding flow for new Telegram users.
-- Phases: restaurant_name -> person_name -> relationship -> city_state
--         -> savings_opportunity -> completed
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.finance_onboarding (
    id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id  BIGINT          NOT NULL,
    status            VARCHAR(50)     DEFAULT 'in_progress',          -- in_progress, completed, abandoned
    current_phase     VARCHAR(50)     DEFAULT 'restaurant_name',      -- restaurant_name, person_name, relationship, city_state, savings_opportunity, completed
    restaurant_name   VARCHAR(255),
    person_name       VARCHAR(255),
    is_owner          BOOLEAN,
    relationship      VARCHAR(100),                                   -- owner, manager, chef, finance
    city              VARCHAR(100),
    state             VARCHAR(2),                                     -- SP, RJ, MG, etc.
    savings_opportunity TEXT,                                         -- Free-text answer saved to memory
    restaurant_id     INTEGER         REFERENCES restaurants(id),
    person_id         INTEGER         REFERENCES restaurant_people(id),
    started_at        TIMESTAMPTZ     DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ     DEFAULT NOW(),
    updated_at        TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finance_onboarding_chat_id
    ON public.finance_onboarding(telegram_chat_id);

CREATE INDEX IF NOT EXISTS idx_finance_onboarding_restaurant
    ON public.finance_onboarding(restaurant_id);


-- ---------------------------------------------------------------------------
-- INVOICES (Nota Fiscal storage)
-- Stores uploaded invoice images and their parsed results.
-- Linked to the restaurant, the uploading person, and optionally to a
-- supplier and purchase order from the procurement system.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.invoices (
    id                        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id             INTEGER         NOT NULL REFERENCES restaurants(id),
    uploaded_by_person_id     INTEGER         REFERENCES restaurant_people(id),
    telegram_chat_id          BIGINT,
    telegram_file_id          VARCHAR(255),
    telegram_file_url         TEXT,
    storage_path              TEXT,
    -- Supplier linkage (extracted from invoice, then matched)
    supplier_name_extracted   VARCHAR(255),
    supplier_cnpj_extracted   VARCHAR(20),
    users_seller_id           INTEGER         REFERENCES suppliers(id),
    master_seller_id          INTEGER,                                -- Future: universal seller registry
    -- Invoice metadata
    invoice_number            VARCHAR(100),
    invoice_date              DATE,
    invoice_type              VARCHAR(50)     DEFAULT 'nf-e',         -- nf-e, cupom_fiscal, nfce, manual
    -- Totals
    subtotal                  NUMERIC(12,2),
    tax_amount                NUMERIC(12,2),
    total_amount              NUMERIC(12,2),
    currency                  VARCHAR(3)      DEFAULT 'BRL',
    -- Purchase order linkage (procurement integration)
    purchase_order_id         VARCHAR         REFERENCES purchase_orders(order_id),
    -- Parsing results
    parsed_at                 TIMESTAMPTZ,
    parsing_confidence        NUMERIC(3,2),
    raw_extraction_result     JSONB,
    status                    VARCHAR(50)     DEFAULT 'uploaded',     -- uploaded, parsing, parsed, confirmed, error
    user_confirmed            BOOLEAN         DEFAULT FALSE,
    created_at                TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_invoices_restaurant
    ON public.invoices(restaurant_id);

CREATE INDEX IF NOT EXISTS idx_invoices_seller
    ON public.invoices(users_seller_id);

CREATE INDEX IF NOT EXISTS idx_invoices_date
    ON public.invoices(invoice_date);

CREATE INDEX IF NOT EXISTS idx_invoices_purchase_order
    ON public.invoices(purchase_order_id);


-- ---------------------------------------------------------------------------
-- INVOICE LINE ITEMS
-- Individual products extracted from each invoice.
-- Price trend fields (previous_price, price_change_percent, price_trend)
-- are computed after storage by comparing to historical data.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.invoice_line_items (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_id              UUID            NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    product_name_raw        VARCHAR(500),                             -- Exactly as printed on the NF
    product_code_raw        VARCHAR(100),                             -- NCM or supplier code
    master_list_id          BIGINT          REFERENCES master_list(id),
    quantity                NUMERIC(12,3),
    unit                    VARCHAR(20),                              -- kg, un, cx, lt
    unit_price              NUMERIC(10,4),
    total_price             NUMERIC(12,2),
    tax_amount              NUMERIC(10,2),
    -- Price trend (computed after storage)
    previous_price          NUMERIC(10,4),
    price_change_percent    NUMERIC(6,2),
    price_trend             VARCHAR(10),                              -- up, down, stable, new
    is_significant_change   BOOLEAN         DEFAULT FALSE,
    extraction_confidence   NUMERIC(3,2),
    line_index              INTEGER,
    created_at              TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_line_items_invoice
    ON public.invoice_line_items(invoice_id);

CREATE INDEX IF NOT EXISTS idx_line_items_master
    ON public.invoice_line_items(master_list_id);

CREATE INDEX IF NOT EXISTS idx_line_items_significant_change
    ON public.invoice_line_items(is_significant_change)
    WHERE is_significant_change = TRUE;
