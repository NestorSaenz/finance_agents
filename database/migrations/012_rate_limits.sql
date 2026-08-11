-- Migration 012: per-user chat rate limits (LLM cost / abuse control).
--
-- Cloud Run is multi-instance and scales to zero, so counters can't live in
-- process memory. Each (user, bucket, window_start) row is a counter for one
-- fixed window: the current minute (burst guard) or the current UTC day (text /
-- image daily allowance). The backend increments them through check_rate_limit;
-- the service owns the thresholds, so the function only returns the new count.

CREATE TABLE IF NOT EXISTS rate_limits (
    user_id UUID NOT NULL,
    bucket TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, bucket, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_user_bucket
    ON rate_limits (user_id, bucket);

-- Row Level Security, matching every sibling table: each user only sees and
-- manages their own counters. The backend uses the service key (bypasses RLS);
-- these policies are defense-in-depth for any direct table access via a JWT.
ALTER TABLE rate_limits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own rate limits" ON rate_limits;
CREATE POLICY "Users can view own rate limits" ON rate_limits
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage own rate limits" ON rate_limits;
CREATE POLICY "Users can manage own rate limits" ON rate_limits
    FOR ALL USING (auth.uid() = user_id);

-- Atomic increment for one window. Self-cleans this user's older windows for the
-- bucket, upserts the current window (+1) and returns the post-increment count in
-- a single round trip. SECURITY DEFINER so it runs regardless of the caller's RLS;
-- it is scoped by p_user_id, which the backend passes from the authenticated context.
-- IMPORTANT: because it trusts p_user_id (no auth.uid() check) and only ever adds 1,
-- exposing it to anon/authenticated would let anyone inflate ANOTHER user's counter
-- and lock them out of chat. Only the backend (service key) may call it.
CREATE OR REPLACE FUNCTION check_rate_limit(
    p_user_id UUID,
    p_bucket TEXT,
    p_window_start TIMESTAMPTZ
) RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_count INT;
BEGIN
    DELETE FROM rate_limits
    WHERE user_id = p_user_id
      AND bucket = p_bucket
      AND window_start < p_window_start;

    INSERT INTO rate_limits (user_id, bucket, window_start, count)
    VALUES (p_user_id, p_bucket, p_window_start, 1)
    ON CONFLICT (user_id, bucket, window_start)
    DO UPDATE SET count = rate_limits.count + 1
    RETURNING count INTO v_count;

    RETURN v_count;
END;
$$;

-- Backend-only: the service key calls this, never the public anon/authenticated JWT.
REVOKE ALL ON FUNCTION check_rate_limit(UUID, TEXT, TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION check_rate_limit(UUID, TEXT, TIMESTAMPTZ)
    TO service_role;
