-- ═══════════════════════════════════════════════════════════════
-- Ashley AI Agent - Multi-User Migration
-- Run this in Supabase SQL Editor AFTER the initial setup
-- ═══════════════════════════════════════════════════════════════

-- 1. Create users table
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_chat_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    timezone TEXT DEFAULT 'Asia/Manila',
    google_token JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on users" ON users FOR ALL USING (true) WITH CHECK (true);

-- 2. Add user_id to contacts
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 3. Add user_id to tasks
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 4. Add user_id to email_queue
ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 5. Add user_id to email_analysis
ALTER TABLE email_analysis ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 6. Add user_id to leads
ALTER TABLE leads ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 7. Add user_id to outreach_messages
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 8. Add user_id to jobs (optional - jobs can be shared or per-user)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 9. Add user_id to applications
ALTER TABLE applications ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 10. Add user_id to cv
ALTER TABLE cv ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 11. Add user_id to experiences
ALTER TABLE experiences ADD COLUMN IF NOT EXISTS user_id TEXT;

-- 12. Create indexes for user_id lookups
CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_email_queue_user ON email_queue(user_id);
CREATE INDEX IF NOT EXISTS idx_email_analysis_user ON email_analysis(user_id);
CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id);
CREATE INDEX IF NOT EXISTS idx_outreach_user ON outreach_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_cv_user ON cv(user_id);
CREATE INDEX IF NOT EXISTS idx_users_chat_id ON users(telegram_chat_id);

-- 13. Migrate existing data to the first admin user
-- Replace '5448864853' with your actual Telegram chat ID
-- This assigns all existing data to you (Anasopie)
UPDATE contacts SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE tasks SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE email_queue SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE email_analysis SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE leads SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE outreach_messages SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE jobs SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE applications SET user_id = '5448864853' WHERE user_id IS NULL;
UPDATE cv SET user_id = '5448864853' WHERE user_id IS NULL;

-- 14. Insert you (Anasopie) as the first admin user
INSERT INTO users (telegram_chat_id, name, email, timezone, is_admin, is_active)
VALUES ('5448864853', 'Anasopie', 'anasopie2@gmail.com', 'Asia/Manila', TRUE, TRUE)
ON CONFLICT (telegram_chat_id) DO NOTHING;
