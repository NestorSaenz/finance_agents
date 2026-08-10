-- Migration 011: goal contributions history (dated aportes).
--
-- A goal used to track only a running `current_amount`, so it showed the same
-- total in every month and couldn't reflect per-month progress. Contributions
-- are now stored as DATED rows (mirroring card_payments), so a goal's progress
-- for a month = the sum of its contributions up to that month-end (cumulative,
-- never reset).

CREATE TABLE IF NOT EXISTS goal_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    contribution_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_goal_contributions_user_goal
    ON goal_contributions (user_id, goal_id);
CREATE INDEX IF NOT EXISTS idx_goal_contributions_date
    ON goal_contributions (user_id, contribution_date);

-- Row Level Security, matching every sibling table (goals, card_payments):
-- each user only sees and manages their own contributions.
ALTER TABLE goal_contributions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own goal contributions" ON goal_contributions;
CREATE POLICY "Users can view own goal contributions" ON goal_contributions
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage own goal contributions" ON goal_contributions;
CREATE POLICY "Users can manage own goal contributions" ON goal_contributions
    FOR ALL USING (auth.uid() = user_id);

-- Backfill: preserve each existing goal's progress as a single initial
-- contribution dated at the goal's creation, so no progress is lost. Idempotent:
-- only for goals with progress and no contributions yet.
INSERT INTO goal_contributions (goal_id, user_id, amount, contribution_date, created_at)
SELECT id, user_id, current_amount, created_at::date, created_at
FROM goals
WHERE current_amount > 0
  AND NOT EXISTS (
    SELECT 1 FROM goal_contributions gc WHERE gc.goal_id = goals.id
  );
