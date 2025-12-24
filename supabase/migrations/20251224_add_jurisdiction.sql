-- Add jurisdiction to cases table
ALTER TABLE cases ADD COLUMN IF NOT EXISTS jurisdiction TEXT DEFAULT 'Florida' 
  CHECK (jurisdiction IN ('Florida', 'New Mexico'));

-- Add default_jurisdiction to profiles for user preferences
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS default_jurisdiction TEXT DEFAULT 'Florida'
  CHECK (default_jurisdiction IN ('Florida', 'New Mexico'));

-- Index for filtering cases by jurisdiction
CREATE INDEX IF NOT EXISTS idx_cases_jurisdiction ON cases(jurisdiction);

