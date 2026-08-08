-- Migration 010: budget attribution date (impact date).
--
-- A credit-card purchase affects the budget of the month its statement is PAID,
-- not the month it was bought (a purchase after the cutoff rolls into a later
-- month). ``budget_date`` holds that impact date; for cash/debit it equals
-- ``transaction_date``. Budgets are evaluated on ``budget_date`` so a mid-cycle
-- credit purchase lands on the month the user actually pays it.

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS budget_date DATE;

-- Backfill existing rows to preserve today's behavior (impact = purchase date).
UPDATE transactions SET budget_date = transaction_date WHERE budget_date IS NULL;

-- Budgets filter/aggregate by budget_date.
CREATE INDEX IF NOT EXISTS idx_transactions_user_budget_date
    ON transactions (user_id, budget_date);

-- Budget spending now sums by budget_date (impact/payment month). COALESCE keeps
-- it correct for any row where budget_date is missing (falls back to purchase date).
CREATE OR REPLACE FUNCTION sum_expenses(
    p_user_id UUID,
    p_category TEXT,
    p_start DATE,
    p_end DATE
) RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(SUM(amount), 0)
    FROM transactions
    WHERE user_id = p_user_id
      AND type = 'expense'
      AND COALESCE(budget_date, transaction_date) BETWEEN p_start AND p_end
      AND (p_category IS NULL OR category = p_category);
$$;
