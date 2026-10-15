-- Run this in Supabase SQL Editor (https://supabase.com/dashboard → SQL Editor)

-- Contacts table
CREATE TABLE IF NOT EXISTS contacts (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Email Queue table
CREATE TABLE IF NOT EXISTS email_queue (
    id BIGSERIAL PRIMARY KEY,
    recipient_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_content TEXT NOT NULL,
    scheduled_time TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'Pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Email Analysis table (stores Ashley's reasoning about each email)
CREATE TABLE IF NOT EXISTS email_analysis (
    id BIGSERIAL PRIMARY KEY,
    message_id TEXT UNIQUE NOT NULL,
    sender_name TEXT,
    sender_email TEXT,
    subject TEXT,
    category TEXT,
    urgency TEXT,
    spam_score INTEGER DEFAULT 0,
    is_suspicious BOOLEAN DEFAULT FALSE,
    sender_type TEXT,
    suggested_action TEXT,
    summary TEXT,
    analyzed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Leads table (businesses scraped from Google Maps)
CREATE TABLE IF NOT EXISTS leads (
    id BIGSERIAL PRIMARY KEY,
    place_id TEXT UNIQUE,
    business_name TEXT NOT NULL,
    category TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    website TEXT,
    rating NUMERIC,
    review_count INTEGER DEFAULT 0,
    google_maps_url TEXT,
    website_analysis TEXT,
    business_needs TEXT,
    lead_score INTEGER DEFAULT 0,
    status TEXT DEFAULT 'new',
    search_query TEXT,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

-- Outreach Messages table
CREATE TABLE IF NOT EXISTS outreach_messages (
    id BIGSERIAL PRIMARY KEY,
    lead_id BIGINT REFERENCES leads(id),
    recipient_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_content TEXT NOT NULL,
    service_offered TEXT,
    status TEXT DEFAULT 'draft',
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ Job Search Tables (shared with job_search_assistant) ═══

-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT DEFAULT '',
    salary TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency TEXT DEFAULT 'USD',
    description TEXT DEFAULT '',
    application_link TEXT NOT NULL,
    posted_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    content_hash TEXT,
    is_expired BOOLEAN DEFAULT FALSE
);

-- Applications table
CREATE TABLE IF NOT EXISTS applications (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
    match_score INTEGER NOT NULL,
    summary TEXT NOT NULL,
    draft_email TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);

-- CV table
CREATE TABLE IF NOT EXISTS cv (
    id BIGSERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    filename TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Experiences table
CREATE TABLE IF NOT EXISTS experiences (
    id BIGSERIAL PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ,
    description TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Job indexes
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_expired ON jobs(is_expired);
CREATE INDEX IF NOT EXISTS idx_jobs_salary ON jobs(salary_min, salary_max);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);
CREATE INDEX IF NOT EXISTS idx_jobs_content_hash ON jobs(content_hash);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_score ON applications(match_score);

-- Enable Row Level Security (but allow all for anon key)
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE outreach_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow all on contacts" ON contacts FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on tasks" ON tasks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on email_queue" ON email_queue FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on email_analysis" ON email_analysis FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on leads" ON leads FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on outreach_messages" ON outreach_messages FOR ALL USING (true) WITH CHECK (true);
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE cv ENABLE ROW LEVEL SECURITY;
ALTER TABLE experiences ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all on jobs" ON jobs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on applications" ON applications FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on cv" ON cv FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all on experiences" ON experiences FOR ALL USING (true) WITH CHECK (true);
