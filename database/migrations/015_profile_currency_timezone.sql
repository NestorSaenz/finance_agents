-- Migration 015: per-user display currency and timezone on the user profile.
--
-- currency: ISO-4217 code used to LABEL the user's amounts (display only — no
-- conversion, no multi-currency accounting). Nullable; the app falls back to
-- DEFAULT_CURRENCY when unset. The code validates the value against a canonical
-- ISO-4217 set before writing, so no DB check constraint is needed here.
-- timezone: IANA timezone, store-only for now (a later cut wires scheduling).
--
-- Idempotent: safe to re-run.

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS timezone TEXT;
