-- Migration 004: long-term user memory (extracted facts).
--
-- The Memory Agent extracts durable facts about the user (goals, income,
-- habits, preferences) from conversations and stores them as key/value pairs.
-- UNIQUE(user_id, key) lets us upsert: a new fact for an existing key updates it.

CREATE TABLE IF NOT EXISTS user_knowledge (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_user_knowledge_user ON user_knowledge (user_id);

ALTER TABLE user_knowledge ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own knowledge" ON user_knowledge
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own knowledge" ON user_knowledge
    FOR ALL USING (auth.uid() = user_id);
