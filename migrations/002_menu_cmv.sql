-- ============================================================================
-- Migration 002: Menu & CMV (Custo de Mercadoria Vendida) Tables
-- Frepi Finance Agent - Supabase PostgreSQL
--
-- Creates:
--   - menu_items            : Restaurant menu with sale prices and CMV metrics
--   - menu_item_ingredients : Recipe cards linking menu items to master_list
--   - menu_cost_history     : Time-series snapshots of cost evolution
--
-- References existing procurement tables:
--   restaurants(id), master_list(id)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- MENU ITEMS
-- Each restaurant's menu with sale prices and computed profitability.
-- food_cost and related fields are recalculated when ingredient prices change.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.menu_items (
    id                    UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id         INTEGER         NOT NULL REFERENCES restaurants(id),
    item_name             VARCHAR(255)    NOT NULL,
    item_description      TEXT,
    category              VARCHAR(100),                               -- entrada, prato_principal, sobremesa, bebida
    sale_price            NUMERIC(10,2)   NOT NULL,
    -- Calculated CMV fields
    food_cost             NUMERIC(10,2),
    food_cost_percent     NUMERIC(5,2),
    contribution_margin   NUMERIC(10,2),
    profitability_tier    VARCHAR(20),                                -- high, medium, low, negative
    is_active             BOOLEAN         DEFAULT TRUE,
    serves_count          INTEGER         DEFAULT 1,
    average_daily_sales   INTEGER,
    -- External system IDs (POS, iFood, Rappi, etc.)
    external_ids          JSONB,                                     -- {"pos_system": "id", "ifood": "id", ...}
    created_at            TIMESTAMPTZ     DEFAULT NOW(),
    updated_at            TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_menu_items_restaurant
    ON public.menu_items(restaurant_id);

CREATE INDEX IF NOT EXISTS idx_menu_items_profitability
    ON public.menu_items(restaurant_id, profitability_tier);


-- ---------------------------------------------------------------------------
-- MENU ITEM INGREDIENTS (Recipe Card)
-- Links each menu item to its ingredient list from the master_list.
-- Cost fields are refreshed from the latest pricing_history or invoices.
-- waste_percent accounts for prep loss (e.g., 10% for trimming meat).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.menu_item_ingredients (
    id                        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    menu_item_id              UUID            NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    master_list_id            BIGINT          REFERENCES master_list(id),
    ingredient_name           VARCHAR(255)    NOT NULL,
    quantity_per_serving      NUMERIC(10,4)   NOT NULL,
    unit                      VARCHAR(20)     NOT NULL,               -- kg, g, un, ml, lt
    -- Cost (computed from latest pricing/invoices)
    current_unit_cost         NUMERIC(10,4),
    cost_per_serving          NUMERIC(10,4),
    cost_source               VARCHAR(50),                           -- pricing_history, invoice_latest, manual
    cost_last_updated         TIMESTAMPTZ,
    waste_percent             NUMERIC(5,2)    DEFAULT 0,
    adjusted_cost_per_serving NUMERIC(10,4),
    created_at                TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingredients_menu_item
    ON public.menu_item_ingredients(menu_item_id);

CREATE INDEX IF NOT EXISTS idx_ingredients_master_list
    ON public.menu_item_ingredients(master_list_id);


-- ---------------------------------------------------------------------------
-- MENU COST HISTORY (CMV Tracking)
-- Time-series snapshots at daily, weekly, or monthly granularity.
-- Tracks how food cost evolves and which ingredient is the primary driver
-- of cost changes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.menu_cost_history (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    menu_item_id                UUID            NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    restaurant_id               INTEGER         NOT NULL REFERENCES restaurants(id),
    snapshot_date               DATE            NOT NULL,
    granularity                 VARCHAR(10)     NOT NULL,             -- daily, weekly, monthly
    sale_price                  NUMERIC(10,2),
    food_cost                   NUMERIC(10,2),
    food_cost_percent           NUMERIC(5,2),
    contribution_margin         NUMERIC(10,2),
    ingredient_costs            JSONB,                               -- [{ingredient, unit_cost, qty, cost}]
    cost_change_from_previous   NUMERIC(10,2),
    cost_change_percent         NUMERIC(6,2),
    primary_driver              VARCHAR(255),                        -- Which ingredient drove the change
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),

    UNIQUE(menu_item_id, snapshot_date, granularity)
);

CREATE INDEX IF NOT EXISTS idx_cost_history_item_date
    ON public.menu_cost_history(menu_item_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_cost_history_restaurant_date
    ON public.menu_cost_history(restaurant_id, snapshot_date);
