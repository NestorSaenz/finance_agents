-- Migration 014: budget spending excludes recurring (fixed) expenses.
--
-- A budget/tope is meant to watch the spending you can CONTROL. Recurring
-- expenses (rent, subscriptions) are predictable — they'd always sit at the cap,
-- so counting them makes the "90%" alert noise. Movements materialized from a
-- recurrente carry `recurring_id`; exclude them so the budget measures VARIABLE
-- (discretionary) spending only. Non-recurring movements keep recurring_id NULL.
--
-- Preserves migration 010's budget_date attribution (impact/payment month): the
-- only change vs 010 is the added `recurring_id IS NULL` predicate.
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
      AND recurring_id IS NULL
      AND COALESCE(budget_date, transaction_date) BETWEEN p_start AND p_end
      AND (p_category IS NULL OR category = p_category);
$$;
