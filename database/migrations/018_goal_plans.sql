-- Migration 018: goal_plans (monthly savings plan per goal) + goal_monthly_contributions.
--
-- A goal only stored its running total, so there was no way to PLAN how much to put
-- toward it each month and compare plan vs what was actually contributed. A plan is
-- neither an expense nor a tope (budget): it never touches budgets/transactions.
--
-- goal_plans keeps the plan WITH HISTORY as two kinds of rows per (goal, month):
--   kind = 'recurring' : "from month M on, X per month"  (carries forward)
--   kind = 'override'  : "in month M exactly X"          (0 = this month I don't plan)
-- The plan of a month is resolved in code (app/src/goals/planning.py):
--   override for the month > latest recurring starting on/before it > no plan.
-- Changing the recurring "from now on" adds/updates a recurring row at the current
-- month, so earlier months keep resolving to the previous recurring (history is
-- never rewritten).
--
-- goal_monthly_contributions(...) returns the GROSS monthly contributed amount per
-- goal (saved = sum of positive aportes, withdrawn = sum of |negative| retiros),
-- grouped by the month of contribution_date. Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS goal_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    month DATE NOT NULL,
    planned_amount NUMERIC(12, 2) NOT NULL,
    kind TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Constraints are added in guarded blocks so re-running the migration is a no-op
-- (ALTER TABLE ... ADD CONSTRAINT has no IF NOT EXISTS).
DO $$
BEGIN
    -- `month` always stores the FIRST day of the month.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'goal_plans_month_first_day'
          AND conrelid = 'goal_plans'::regclass
    ) THEN
        ALTER TABLE goal_plans
            ADD CONSTRAINT goal_plans_month_first_day
            CHECK (EXTRACT(DAY FROM month) = 1);
    END IF;

    -- A plan is never negative (0 means "no savings planned this month").
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'goal_plans_planned_amount_nonneg'
          AND conrelid = 'goal_plans'::regclass
    ) THEN
        ALTER TABLE goal_plans
            ADD CONSTRAINT goal_plans_planned_amount_nonneg
            CHECK (planned_amount >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'goal_plans_kind_valid'
          AND conrelid = 'goal_plans'::regclass
    ) THEN
        ALTER TABLE goal_plans
            ADD CONSTRAINT goal_plans_kind_valid
            CHECK (kind IN ('recurring', 'override'));
    END IF;

    -- One row per (goal, month, kind): the target of the repository's upsert
    -- (on_conflict = goal_id,month,kind).
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'goal_plans_goal_month_kind_key'
          AND conrelid = 'goal_plans'::regclass
    ) THEN
        ALTER TABLE goal_plans
            ADD CONSTRAINT goal_plans_goal_month_kind_key
            UNIQUE (goal_id, month, kind);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_goal_plans_user_goal_month
    ON goal_plans (user_id, goal_id, month);

-- Row Level Security, same policies as goal_contributions (011): each user only
-- sees and manages their own plans.
ALTER TABLE goal_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own goal plans" ON goal_plans;
CREATE POLICY "Users can view own goal plans" ON goal_plans
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage own goal plans" ON goal_plans;
CREATE POLICY "Users can manage own goal plans" ON goal_plans
    FOR ALL USING (auth.uid() = user_id);

-- Gross contributed per goal and month in [p_start, p_end] (inclusive).
--   saved     = sum of positive aportes
--   withdrawn = sum of the absolute value of negative aportes (retiros)
-- Months with no movement produce no row.
CREATE OR REPLACE FUNCTION goal_monthly_contributions(
    p_user_id UUID,
    p_start DATE,
    p_end DATE
) RETURNS TABLE(goal_id UUID, month DATE, saved NUMERIC, withdrawn NUMERIC)
LANGUAGE sql
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT gc.goal_id,
           date_trunc('month', gc.contribution_date)::date AS month,
           COALESCE(SUM(gc.amount) FILTER (WHERE gc.amount > 0), 0) AS saved,
           COALESCE(SUM(-gc.amount) FILTER (WHERE gc.amount < 0), 0) AS withdrawn
    FROM goal_contributions gc
    WHERE gc.user_id = p_user_id
      AND gc.contribution_date BETWEEN p_start AND p_end
    GROUP BY gc.goal_id, date_trunc('month', gc.contribution_date)
    ORDER BY 1, 2;
$$;

-- Only the backend (service_role) may execute it: it trusts p_user_id. REVOKE FROM
-- PUBLIC alone is not enough on Supabase (anon/authenticated hold EXECUTE through
-- default privileges), so they are revoked explicitly (same pattern as 017).
REVOKE ALL ON FUNCTION goal_monthly_contributions(UUID, DATE, DATE)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION goal_monthly_contributions(UUID, DATE, DATE)
    TO service_role;

-- Make PostgREST see the new table/RPC without waiting for its schema cache refresh.
NOTIFY pgrst, 'reload schema';
