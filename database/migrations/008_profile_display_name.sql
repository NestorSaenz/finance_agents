-- Migration 008: display name on the user profile.
--
-- Captured during onboarding so the assistant can address the user by name for
-- a warmer, less impersonal tone. Nullable (the user may skip it).

ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS display_name TEXT;
