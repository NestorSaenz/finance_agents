-- Migration 001: denormalized `category` column on transactions.
--
-- The domain layer and the AI agents (categorizer, analyst) work with the
-- CategoryType enum (lowercase Spanish slugs, e.g. 'restaurantes'). The original
-- schema only stored `category_id` (FK to the `categories` table), which would
-- require a per-row join/lookup to resolve the slug. For the MVP we store the
-- AI/selected category slug directly so persistence stays consistent with the
-- rest of the codebase. `category_id` remains reserved for user-defined
-- categories.

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS category TEXT;

-- Index to support filtering transactions by category per user.
CREATE INDEX IF NOT EXISTS idx_transactions_user_category
    ON transactions (user_id, category);
