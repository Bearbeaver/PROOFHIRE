-- ProofHire relational schema (design Section 6). Written for SQLite; portable to PostgreSQL by
-- swapping TEXT-JSON columns for JSONB, TEXT timestamps for TIMESTAMPTZ and INTEGER booleans for BOOLEAN.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('CANDIDATE','RECRUITER','ADMIN')),
  status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','REMOVED')),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate (
  id TEXT PRIMARY KEY REFERENCES users(id),
  bio TEXT NOT NULL DEFAULT '',
  skills TEXT NOT NULL DEFAULT '[]',
  portfolio_links TEXT NOT NULL DEFAULT '[]',
  field TEXT NOT NULL DEFAULT 'Backend Engineering'
);

CREATE TABLE IF NOT EXISTS recruiter (
  id TEXT PRIMARY KEY REFERENCES users(id),
  company TEXT NOT NULL DEFAULT '',
  search_history TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS admin (
  id TEXT PRIMARY KEY REFERENCES users(id),
  permissions TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS submission (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  title TEXT NOT NULL,
  skill_area TEXT NOT NULL,
  date_submitted TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING','QUEUED','SCORED','RESUBMITTED')),
  resubmission_count INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  moderation TEXT NOT NULL DEFAULT 'NONE' CHECK (moderation IN ('NONE','FLAGGED','REMOVED')),
  flag_reason TEXT,
  flagged_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_submission_candidate_status ON submission(candidate_id, status);
CREATE INDEX IF NOT EXISTS idx_submission_skill_area ON submission(skill_area);
CREATE INDEX IF NOT EXISTS idx_submission_status ON submission(status);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES submission(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('GITHUB','PORTFOLIO','CERTIFICATE')),
  url TEXT,
  file_ref TEXT,
  file_name TEXT,
  description TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_evidence_submission ON evidence(submission_id);

CREATE TABLE IF NOT EXISTS proof_score (
  id TEXT PRIMARY KEY,
  submission_id TEXT NOT NULL REFERENCES submission(id) ON DELETE CASCADE,
  overall_score REAL NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
  sub_scores TEXT NOT NULL,
  recommendations TEXT NOT NULL,
  strengths TEXT NOT NULL DEFAULT '[]',
  facts TEXT NOT NULL DEFAULT '[]',
  attempt_no INTEGER NOT NULL,
  scored_at TEXT NOT NULL,
  model_version TEXT,
  data_quality TEXT
);
CREATE INDEX IF NOT EXISTS idx_proof_score_submission ON proof_score(submission_id, attempt_no);
CREATE INDEX IF NOT EXISTS idx_proof_score_overall ON proof_score(overall_score);

CREATE TABLE IF NOT EXISTS shortlist (
  id TEXT PRIMARY KEY,
  recruiter_id TEXT NOT NULL REFERENCES recruiter(id),
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  created_at TEXT NOT NULL,
  UNIQUE (recruiter_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS contact_request (
  id TEXT PRIMARY KEY,
  recruiter_id TEXT NOT NULL REFERENCES recruiter(id),
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  message TEXT NOT NULL,
  sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  actor_id TEXT NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,
  target_type TEXT,
  target_id TEXT,
  detail TEXT,
  timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(timestamp);

CREATE TABLE IF NOT EXISTS system_config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
  id TEXT PRIMARY KEY,
  recruiter_id TEXT NOT NULL REFERENCES recruiter(id),
  title TEXT NOT NULL,
  company TEXT NOT NULL,
  field TEXT NOT NULL,
  location TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  skills TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL,
  message TEXT NOT NULL,
  link TEXT,
  created_at TEXT NOT NULL,
  is_read INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_notification_user ON notification(user_id, is_read);

CREATE TABLE IF NOT EXISTS assessment_attempt (
  id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES candidate(id),
  field TEXT NOT NULL,
  correct INTEGER NOT NULL,
  total INTEGER NOT NULL,
  passed INTEGER NOT NULL,
  taken_at TEXT NOT NULL,
  valid_until TEXT
);
CREATE INDEX IF NOT EXISTS idx_assessment_candidate ON assessment_attempt(candidate_id, field);

CREATE TABLE IF NOT EXISTS profile_view (
  id TEXT PRIMARY KEY, recruiter_id TEXT NOT NULL, candidate_id TEXT NOT NULL, viewed_at TEXT NOT NULL
);
