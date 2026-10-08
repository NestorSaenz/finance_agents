-- Migration 016: pending actions (propose in one chat turn, confirm in the next).
--
-- Some chat actions (changing a card's cutoff/payment day) must be applied ONLY
-- after the user's later confirmation, enforced in code rather than by prompt
-- wording. The agent proposes in turn N (a row is stored); the user's "sí" in a
-- LATER turn consumes it. Cloud Run is multi-instance, so the state lives here and
-- consume/discard are atomic SQL functions (the DatabaseInterface only filters on
-- equality, so a select-then-delete would race). One row per (user, conversation).

CREATE TABLE IF NOT EXISTS pending_actions (
    user_id UUID NOT NULL,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    payload JSONB NOT NULL,
    turn_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, conversation_id)
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_expires
    ON pending_actions (expires_at);

-- Row Level Security. The backend uses the service key (bypasses RLS); the policy
-- below is defense-in-depth for JWT access.
ALTER TABLE pending_actions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can manage own pending actions" ON pending_actions;
DROP POLICY IF EXISTS "Users can view own pending actions" ON pending_actions;
CREATE POLICY "Users can view own pending actions" ON pending_actions
    FOR SELECT USING (auth.uid() = user_id);

-- SELECT-only: users never write this table; the backend (service key) does.

-- Atomically take the user's live proposal for this conversation/kind and return
-- its payload (NULL when there is none). Replay-safe (the DELETE consumes it, so a
-- second call gets NULL) and it only matches a proposal made in an EARLIER turn
-- (turn_id <> p_turn_id), so the turn that proposed can never confirm it.
-- SECURITY DEFINER + scoped by p_user_id: only the backend (service key) may call
-- it (see the REVOKE/GRANT below). Pinned search_path: required for SECURITY DEFINER.
CREATE OR REPLACE FUNCTION consume_pending_action(
    p_user_id UUID,
    p_conversation_id UUID,
    p_kind TEXT,
    p_turn_id TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_payload JSONB;
BEGIN
    DELETE FROM pending_actions
    WHERE user_id = p_user_id
      AND expires_at < NOW();

    DELETE FROM pending_actions
    WHERE user_id = p_user_id
      AND conversation_id = p_conversation_id
      AND kind = p_kind
      AND turn_id <> p_turn_id
      AND expires_at >= NOW()
    RETURNING payload INTO v_payload;

    RETURN v_payload;
END;
$$;

-- End-of-turn sweep: drop this user's expired rows and this conversation's rows
-- whose turn is not the one that just ran, so a proposal is only valid in the very
-- next user turn (a later unrelated message cancels it).
CREATE OR REPLACE FUNCTION discard_stale_pending_actions(
    p_user_id UUID,
    p_conversation_id UUID,
    p_keep_turn_id TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    DELETE FROM pending_actions
    WHERE user_id = p_user_id
      AND (
          expires_at < NOW()
          OR (conversation_id = p_conversation_id AND turn_id <> p_keep_turn_id)
      );
END;
$$;

-- Only the backend (service_role) may execute these. REVOKE FROM PUBLIC alone is not
-- enough on Supabase: anon/authenticated hold EXECUTE through default privileges, so
-- they are revoked explicitly. Both functions trust p_user_id.
REVOKE ALL ON FUNCTION consume_pending_action(UUID, UUID, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION consume_pending_action(UUID, UUID, TEXT, TEXT)
    TO service_role;

REVOKE ALL ON FUNCTION discard_stale_pending_actions(UUID, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION discard_stale_pending_actions(UUID, UUID, TEXT)
    TO service_role;

-- Same hardening for check_rate_limit from 012 (already deployed). It also trusts
-- p_user_id, so anon/authenticated must not be able to call it. The backend uses the
-- service key, so behaviour is unchanged.
REVOKE ALL ON FUNCTION check_rate_limit(UUID, TEXT, TIMESTAMPTZ)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION check_rate_limit(UUID, TEXT, TIMESTAMPTZ)
    TO service_role;
ALTER FUNCTION check_rate_limit(UUID, TEXT, TIMESTAMPTZ)
    SET search_path = public, pg_temp;
