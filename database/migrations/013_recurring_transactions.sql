-- Migration 013: recurring transactions (monthly templates).
--
-- A recurring transaction is a TEMPLATE for a movement that repeats monthly
-- (a salary, a rent, a subscription). A daily job (POST /recurring/run) reads the
-- due templates and materializes each into a real row in the `transactions` table,
-- then advances the schedule. The template itself is never a movement — it only
-- carries the amount and the schedule.
--
-- The `type` column matches the `transactions` table naming (mapped from the
-- domain's `transaction_type` field).

CREATE TABLE IF NOT EXISTS recurring_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    description TEXT NOT NULL,
    type TEXT NOT NULL,
    category TEXT,
    payment_method TEXT,
    -- Link to the credit card this charge belongs to. ON DELETE SET NULL so
    -- deleting a card never orphans a template with a dangling id; the daily run
    -- then falls back to treating the charge as cash (efectivo).
    card_id UUID REFERENCES credit_cards(id) ON DELETE SET NULL,
    -- Only 'monthly' is supported today; the CHECK keeps the column honest until
    -- weekly/yearly are actually implemented.
    frequency TEXT NOT NULL DEFAULT 'monthly' CHECK (frequency IN ('monthly')),
    day_of_month INT NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    next_run_date DATE NOT NULL,
    last_run_date DATE,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recurring_transactions_user
    ON recurring_transactions (user_id);
-- The daily job scans active templates by next_run_date.
CREATE INDEX IF NOT EXISTS idx_recurring_transactions_due
    ON recurring_transactions (active, next_run_date);

-- Row Level Security, matching every sibling table (goals, card_payments):
-- each user only sees and manages their own recurring templates.
ALTER TABLE recurring_transactions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own recurring transactions" ON recurring_transactions;
CREATE POLICY "Users can view own recurring transactions" ON recurring_transactions
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage own recurring transactions" ON recurring_transactions;
CREATE POLICY "Users can manage own recurring transactions" ON recurring_transactions
    FOR ALL USING (auth.uid() = user_id);

-- ============================================================================
-- Exactly-once materialization (DB-level idempotency).
--
-- The daily run is at-least-once (Cloud Scheduler retries, multiple instances).
-- To guarantee a template's occurrence is materialized AT MOST once, every
-- materialized transaction records which template (recurring_id) and which
-- scheduled date (occurrence_date) it came from, and a UNIQUE index forbids a
-- second row for the same pair. The insert uses ON CONFLICT (recurring_id,
-- occurrence_date) DO NOTHING, so a retry/duplicate is a silent no-op instead of
-- a duplicate charge.
--
-- The index is deliberately NON-partial: a partial index (WHERE recurring_id IS
-- NOT NULL) cannot be inferred by PostgREST's `ON CONFLICT (cols)` unless the
-- predicate is repeated (PostgREST doesn't emit it) → the upsert would raise
-- 42P10 in production. A plain unique index is inferable, and normal
-- (non-recurring) transactions are unaffected because they leave both columns
-- NULL and Postgres treats NULLs as distinct, so (NULL, NULL) rows never collide.
-- ============================================================================
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS recurring_id UUID;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS occurrence_date DATE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_tx_recurring_occurrence
    ON transactions (recurring_id, occurrence_date);
