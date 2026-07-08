-- Migration 002: denormalized `category` column on budgets.
--
-- Mirrors migration 001 for transactions: the domain works with the CategoryType
-- enum slug, while the original schema only stored `category_id` (FK). A NULL
-- category represents an overall (all-categories) budget.

ALTER TABLE budgets
    ADD COLUMN IF NOT EXISTS category TEXT;

CREATE INDEX IF NOT EXISTS idx_budgets_user_category
    ON budgets (user_id, category);
