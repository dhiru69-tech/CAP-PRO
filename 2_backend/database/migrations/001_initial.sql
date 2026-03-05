-- ReconMind — Migration 001: Initial Schema
-- Run this manually if you prefer raw SQL over SQLAlchemy auto-create
-- psql -U postgres -d reconmind -f migrations/001_initial.sql

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────
-- Enums
-- ─────────────────────────────────────────
CREATE TYPE scan_status AS ENUM ('pending', 'running', 'completed', 'failed', 'cancelled');
CREATE TYPE scan_depth AS ENUM ('surface', 'standard', 'deep');
CREATE TYPE finding_risk AS ENUM ('critical', 'high', 'medium', 'low', 'info');

-- ─────────────────────────────────────────
-- Users
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    name            VARCHAR(255),
    picture         TEXT,
    google_id       VARCHAR(255) UNIQUE,
    is_active       BOOLEAN DEFAULT TRUE,
    scan_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_login      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ─────────────────────────────────────────
-- Scans
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scans (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target              VARCHAR(512) NOT NULL,
    depth               scan_depth DEFAULT 'standard',
    status              scan_status DEFAULT 'pending',
    dork_categories     TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    total_dorks         INTEGER DEFAULT 0,
    total_urls_found    INTEGER DEFAULT 0,
    total_findings      INTEGER DEFAULT 0,
    error_message       TEXT,
    ai_summary          TEXT
);

CREATE INDEX IF NOT EXISTS idx_scans_user_id ON scans(user_id);
CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);

-- ─────────────────────────────────────────
-- Dorks
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dorks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id         UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    category        VARCHAR(100) NOT NULL,
    query           TEXT NOT NULL,
    generated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dorks_scan_id ON dorks(scan_id);

-- ─────────────────────────────────────────
-- Results (discovered URLs)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id         UUID NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    dork_id         UUID REFERENCES dorks(id) ON DELETE SET NULL,
    url             TEXT NOT NULL,
    title           TEXT,
    snippet         TEXT,
    http_status     INTEGER,
    is_alive        BOOLEAN,
    risk_level      finding_risk,
    ai_explanation  TEXT,
    found_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_results_scan_id ON results(scan_id);

-- ─────────────────────────────────────────
-- Reports
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scan_id             UUID UNIQUE NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    summary             TEXT,
    ai_analysis         TEXT,
    recommendations     TEXT,
    file_path           TEXT,
    generated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Done
SELECT 'ReconMind schema created successfully.' AS message;
