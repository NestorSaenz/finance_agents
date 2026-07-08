-- Migration 009: credit cards, their payments, and card links on transactions.
--
-- Cards are identified by a human name only (e.g. the bank) — NO card numbers
-- or any sensitive data. cutoff_day/payment_day (1-31) drive the billing cycle.
-- Charges are regular credit expenses linked via transactions.card_id; payments
-- toward the card live in card_payments. Balance = charges - payments.

CREATE TABLE IF NOT EXISTS credit_cards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    credit_limit NUMERIC(14, 2) NOT NULL,
    cutoff_day SMALLINT NOT NULL CHECK (cutoff_day BETWEEN 1 AND 31),
    payment_day SMALLINT NOT NULL CHECK (payment_day BETWEEN 1 AND 31),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_credit_cards_user ON credit_cards (user_id);

CREATE TABLE IF NOT EXISTS card_payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id UUID NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    amount NUMERIC(14, 2) NOT NULL,
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_card_payments_card ON card_payments (user_id, card_id);

-- Link a credit expense to the card it was charged to.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS card_id UUID REFERENCES credit_cards(id);
CREATE INDEX IF NOT EXISTS idx_transactions_card ON transactions (user_id, card_id);

-- RLS: each user only sees their own cards and payments.
ALTER TABLE credit_cards ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view own cards" ON credit_cards;
CREATE POLICY "Users can view own cards" ON credit_cards
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users can manage own cards" ON credit_cards;
CREATE POLICY "Users can manage own cards" ON credit_cards
    FOR ALL USING (auth.uid() = user_id);

ALTER TABLE card_payments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view own card payments" ON card_payments;
CREATE POLICY "Users can view own card payments" ON card_payments
    FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users can manage own card payments" ON card_payments;
CREATE POLICY "Users can manage own card payments" ON card_payments
    FOR ALL USING (auth.uid() = user_id);
