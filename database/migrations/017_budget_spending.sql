-- Migration 017: budget_spending (total + fixed part of a tope's spending).
--
-- Migration 014 made sum_expenses EXCLUDE recurring expenses so a fixed bill would
-- not trip the alert every month. In practice users size their topes to INCLUDE
-- fixed bills (rent, school fees...), so the excluded bar understated real spending
-- (e.g. 17% shown vs 114% real). 014's rationale is superseded: the bar now counts
-- everything and the alert logic (in code) distinguishes the fixed part.
--
-- sum_expenses is intentionally left untouched: already-deployed backend revisions
-- still call it and expect a single number. This NEW function returns both values:
--   total = every expense of the period/category (recurring included)
--   fixed = the part of total that comes from recurring expenses
-- Attribution is by budget_date (credit -> payment month), falling back to
-- transaction_date, exactly like sum_expenses.

CREATE OR REPLACE FUNCTION budget_spending(
    p_user_id UUID,
    p_category TEXT,
    p_start DATE,
    p_end DATE
) RETURNS TABLE(total NUMERIC, fixed NUMERIC)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT COALESCE(SUM(amount), 0),
           COALESCE(SUM(amount) FILTER (WHERE recurring_id IS NOT NULL), 0)
    FROM transactions
    WHERE user_id = p_user_id
      AND type = 'expense'
      AND COALESCE(budget_date, transaction_date) BETWEEN p_start AND p_end
      AND (p_category IS NULL OR category = p_category);
$$;

-- Only the backend (service_role) may execute it: it trusts p_user_id. REVOKE FROM
-- PUBLIC alone is not enough on Supabase (anon/authenticated hold EXECUTE through
-- default privileges), so they are revoked explicitly.
REVOKE ALL ON FUNCTION budget_spending(UUID, TEXT, DATE, DATE)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION budget_spending(UUID, TEXT, DATE, DATE)
    TO service_role;

-- Make PostgREST see the new RPC without waiting for its schema cache refresh.
NOTIFY pgrst, 'reload schema';
