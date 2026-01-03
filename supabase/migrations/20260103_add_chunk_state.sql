-- Add chunk_state JSONB column to analysis_results for chunked processing
-- This stores document processing status, chunk plan, and summaries for recovery

ALTER TABLE public.analysis_results 
ADD COLUMN IF NOT EXISTS chunk_state JSONB DEFAULT '{}'::jsonb;

-- Add index for querying by phase
CREATE INDEX IF NOT EXISTS idx_analysis_chunk_state_phase 
ON public.analysis_results ((chunk_state->>'phase'));

-- Add comment explaining the structure
COMMENT ON COLUMN public.analysis_results.chunk_state IS 
'Stores chunked processing state including:
- config: {max_tokens_per_chunk, created_at}
- chunks: [{index, doc_ids, tokens, status}]
- current_chunk: index of chunk being processed
- phase: document_analysis | synthesis | multi_stage | completed
- documents: {doc_id: {name, status, error, retry_count, summary_key}}
- summaries: {key: {file_name, summary, key_facts}}
- lock: {instance_id, locked_at} for concurrency control';

-- Create function for acquiring processing lock
CREATE OR REPLACE FUNCTION acquire_analysis_lock(
    p_analysis_id UUID,
    p_instance_id TEXT,
    p_timeout_seconds INT DEFAULT 330
) RETURNS JSONB AS $$
DECLARE
    current_lock JSONB;
    lock_time TIMESTAMPTZ;
BEGIN
    SELECT chunk_state->'lock' INTO current_lock
    FROM analysis_results WHERE id = p_analysis_id;
    
    -- Check if lock exists and is not expired
    IF current_lock IS NOT NULL AND current_lock != 'null'::jsonb THEN
        lock_time := (current_lock->>'locked_at')::TIMESTAMPTZ;
        IF lock_time + (p_timeout_seconds || ' seconds')::INTERVAL > NOW() THEN
            RETURN jsonb_build_object('acquired', false, 'reason', 'locked', 'holder', current_lock->>'instance_id');
        END IF;
    END IF;
    
    -- Acquire lock
    UPDATE analysis_results
    SET chunk_state = COALESCE(chunk_state, '{}'::jsonb) || jsonb_build_object(
        'lock', jsonb_build_object('instance_id', p_instance_id, 'locked_at', NOW())
    )
    WHERE id = p_analysis_id;
    
    RETURN jsonb_build_object('acquired', true);
END;
$$ LANGUAGE plpgsql;

-- Create function for releasing lock
CREATE OR REPLACE FUNCTION release_analysis_lock(
    p_analysis_id UUID,
    p_instance_id TEXT
) RETURNS JSONB AS $$
DECLARE
    current_lock JSONB;
BEGIN
    SELECT chunk_state->'lock' INTO current_lock
    FROM analysis_results WHERE id = p_analysis_id;
    
    -- Only release if we hold the lock
    IF current_lock IS NOT NULL AND current_lock->>'instance_id' = p_instance_id THEN
        UPDATE analysis_results
        SET chunk_state = chunk_state - 'lock'
        WHERE id = p_analysis_id;
        RETURN jsonb_build_object('released', true);
    END IF;
    
    RETURN jsonb_build_object('released', false, 'reason', 'not_holder');
END;
$$ LANGUAGE plpgsql;

