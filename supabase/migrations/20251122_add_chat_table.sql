-- Migration: Add case_chat_messages table for AI chat history
-- Date: 2025-11-22

CREATE TABLE IF NOT EXISTS case_chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE NOT NULL,
    user_message TEXT NOT NULL,
    ai_response TEXT NOT NULL,
    context_used JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_case_chat_messages_case_id
    ON case_chat_messages(case_id);

ALTER TABLE case_chat_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view chat messages of own cases"
    ON case_chat_messages FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = case_chat_messages.case_id
              AND cases.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert chat messages to own cases"
    ON case_chat_messages FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = case_chat_messages.case_id
              AND cases.user_id = auth.uid()
        )
    );
