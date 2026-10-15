-- ═══════════════════════════════════════════════════════════════
-- Ashley AI Agent - User Approval System Migration
-- Run this in Supabase SQL Editor
-- ═══════════════════════════════════════════════════════════════

-- 1. Add is_approved column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE;

-- 2. Auto-approve existing admin users (you, Anasopie)
UPDATE users SET is_approved = TRUE WHERE is_admin = TRUE;

-- 3. Auto-approve any existing active users who already have Google connected
--    (they were clearly set up intentionally, so they should be approved)
UPDATE users SET is_approved = TRUE WHERE google_token IS NOT NULL;
