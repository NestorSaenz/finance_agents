-- Migration 007: payment method on transactions.
--
-- Distinguishes real money already spent (efectivo: cash, debit, transfer) from
-- deferred money owed on a credit card (credito). This is the foundation for
-- credit-card control (spent-this-cycle, available credit) built on top later.
-- Nullable: existing rows and expenses where the method wasn't stated stay NULL.

ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS payment_method TEXT
    CHECK (payment_method IN ('efectivo', 'credito'));

-- Support "how much did I pay on credit this month" style queries.
CREATE INDEX IF NOT EXISTS idx_transactions_user_payment_method
    ON transactions (user_id, payment_method);
