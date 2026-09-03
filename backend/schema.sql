-- ======================================================
-- PostgreSQL Schema for Voice AI Personal Assistant
-- ======================================================

-- 1. Businesses Table
CREATE TABLE IF NOT EXISTS businesses (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(128) NOT NULL,
    owner_name VARCHAR(255) NOT NULL,
    phone VARCHAR(64) NOT NULL,
    email VARCHAR(255) NOT NULL,
    address TEXT,
    created_at VARCHAR(64) NOT NULL
);

-- 2. Workflows Table
CREATE TABLE IF NOT EXISTS workflows (
    id VARCHAR(64) PRIMARY KEY,
    business_id VARCHAR(64) NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(128) NOT NULL,
    trigger_event VARCHAR(128) NOT NULL DEFAULT 'Missed Call',
    greeting TEXT NOT NULL,
    fields TEXT NOT NULL, -- JSON string
    conditions TEXT NOT NULL, -- JSON string
    actions TEXT NOT NULL, -- JSON string
    closing_message TEXT NOT NULL,
    language VARCHAR(32) NOT NULL DEFAULT 'en-hi',
    is_active INT NOT NULL DEFAULT 1,
    created_at VARCHAR(64) NOT NULL
);

-- 3. Customer Missed Call Records Table
CREATE TABLE IF NOT EXISTS records (
    id VARCHAR(64) PRIMARY KEY,
    business_id VARCHAR(64) NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    workflow_id VARCHAR(64) NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    caller_name VARCHAR(255) NOT NULL,
    caller_phone VARCHAR(64) NOT NULL,
    intent VARCHAR(255) NOT NULL,
    collected_data TEXT NOT NULL, -- JSON string
    ai_summary TEXT NOT NULL,
    urgency VARCHAR(32) NOT NULL DEFAULT 'Normal', -- Normal, Urgent, Critical
    followup_status VARCHAR(32) NOT NULL DEFAULT 'Pending', -- Pending, Contacted, Completed, Closed
    transcript TEXT NOT NULL, -- JSON string
    tools_executed TEXT NOT NULL, -- JSON string
    created_at VARCHAR(64) NOT NULL
);

-- 4. Google Calendar Events Table
CREATE TABLE IF NOT EXISTS calendar_events (
    id VARCHAR(64) PRIMARY KEY,
    business_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    start_time VARCHAR(64) NOT NULL,
    end_time VARCHAR(64) NOT NULL,
    attendee_name VARCHAR(255) NOT NULL,
    attendee_phone VARCHAR(64) NOT NULL,
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'Confirmed',
    google_event_id VARCHAR(128),
    created_at VARCHAR(64) NOT NULL
);

-- Indexes for High Performance Queries
CREATE INDEX IF NOT EXISTS idx_records_business ON records(business_id);
CREATE INDEX IF NOT EXISTS idx_records_status ON records(followup_status);
CREATE INDEX IF NOT EXISTS idx_workflows_business ON workflows(business_id);
