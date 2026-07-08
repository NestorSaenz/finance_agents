-- Migration 005: server-side expense sum for budget spending.
--
-- Replaces the O(budgets × transactions) client-side scan in
-- TransactionSpendingProvider with a single aggregate query. p_category NULL
-- means "all categories" (an overall budget). SECURITY: the function is scoped
-- by p_user_id, which the backend always passes from the authenticated context.

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
      AND transaction_date BETWEEN p_start AND p_end
      AND (p_category IS NULL OR category = p_category);
$$;
