-- Migration 006: per-user profile / onboarding state.
--
-- Holds the answers collected during the initial onboarding wizard (monthly
-- income) plus a flag so the wizard is only shown once. One row per user
-- (UNIQUE user_id) so we can upsert on user_id.

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    monthly_income NUMERIC(14, 2),
    savings_goal_percentage NUMERIC(5, 2),
    onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id)
);

-- Idempotent: if the table already existed (e.g. from schema.sql) ensure the
-- savings-target column is present.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS savings_goal_percentage NUMERIC(5, 2);

CREATE INDEX IF NOT EXISTS idx_user_profiles_user ON user_profiles (user_id);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Policies use DROP ... IF EXISTS first so this migration is safe to re-run
-- (CREATE POLICY has no IF NOT EXISTS).
DROP POLICY IF EXISTS "Users can view own profile" ON user_profiles;
CREATE POLICY "Users can view own profile" ON user_profiles
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage own profile" ON user_profiles;
CREATE POLICY "Users can manage own profile" ON user_profiles
    FOR ALL USING (auth.uid() = user_id);
