CREATE TABLE prompts (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Function to update updated_at column
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at on row update
CREATE TRIGGER set_timestamp
BEFORE UPDATE ON prompts
FOR EACH ROW
EXECUTE PROCEDURE trigger_set_timestamp();

-- Enable Row Level Security
-- ALTER TABLE prompts ENABLE ROW LEVEL SECURITY;

-- Create policies for prompts table
-- CREATE POLICY "Allow all users to read prompts" ON prompts
--   FOR SELECT USING (TRUE);

-- CREATE POLICY "Allow authenticated users to insert prompts" ON prompts
--   FOR INSERT WITH CHECK (auth.role() = 'authenticated');

-- CREATE POLICY "Allow authenticated users to update their own prompts" ON prompts
--   FOR UPDATE USING (auth.role() = 'authenticated')
--   WITH CHECK (auth.role() = 'authenticated');

-- Note: Deletion of prompts is not allowed through this policy.
-- Consider if you need a specific role or different policy for deletions. 