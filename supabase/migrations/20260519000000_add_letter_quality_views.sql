-- =============================================================================
-- Migration: 20260519000000_add_letter_quality_views.sql
--
-- Operational observability views over existing tables. No new data
-- captured — these just flatten nested JSONB and aggregate counts so
-- common admin questions ("which letters failed QA?", "which cases
-- have docs but no analysis?") are one SELECT instead of a Python
-- script that paginates and walks the JSON tree.
--
-- Why views (not materialized): no users at scale yet; staleness from
-- materialization would obscure real-time signal. Re-evaluate later if
-- the underlying tables grow past ~100k rows.
--
-- Dependencies: analysis_results, cases, analysis_jobs, documents
-- (all present in baseline schema).
-- =============================================================================


-- =============================================================================
-- VIEW: letter_quality_signals
--
-- Flattens analysis_results.result.generated_letters.findings_meta.
-- quality_report.quality_report_v2 into queryable columns, plus a few
-- top-level signals like "did the model recommend a demand letter".
--
-- Only completed analyses included. NULL signals indicate the check
-- wasn't applicable (e.g., demand_specificity_passed is NULL for
-- findings letters — the check only runs on demand letters).
-- =============================================================================

CREATE OR REPLACE VIEW letter_quality_signals AS
SELECT
    ar.id                                                       AS analysis_id,
    ar.case_id,
    c.client_name,
    c.user_id,
    c.jurisdiction,
    ar.completed_at,

    -- Letter presence
    (ar.result -> 'generated_letters' -> 'findings') IS NOT NULL AS has_findings_letter,

    -- Count of demand_<party> letter keys (excludes _meta keys).
    -- Uses jsonb_object_keys; returns 0 when generated_letters is null/empty.
    (
        SELECT COUNT(*)::int
        FROM jsonb_object_keys(
            COALESCE(ar.result -> 'generated_letters', '{}'::jsonb)
        ) AS k
        WHERE k LIKE 'demand_%' AND k NOT LIKE '%_meta'
    )                                                            AS demand_letter_count,

    -- QA v2 signals (lives under findings_meta because that's where
    -- the findings letter's lint runs)
    NULLIF(
        ar.result -> 'generated_letters' -> 'findings_meta'
            -> 'quality_report' -> 'quality_report_v2' ->> 'term_explainer_passed',
        ''
    )::bool                                                      AS qa_term_explainer_passed,

    NULLIF(
        ar.result -> 'generated_letters' -> 'findings_meta'
            -> 'quality_report' -> 'quality_report_v2' ->> 'evidence_linkage_score',
        ''
    )::float                                                     AS qa_evidence_linkage_score,

    NULLIF(
        ar.result -> 'generated_letters' -> 'findings_meta'
            -> 'quality_report' -> 'quality_report_v2' ->> 'section_depth_score',
        ''
    )::float                                                     AS qa_section_depth_score,

    NULLIF(
        ar.result -> 'generated_letters' -> 'findings_meta'
            -> 'quality_report' -> 'quality_report_v2' ->> 'demand_specificity_passed',
        ''
    )::bool                                                      AS qa_demand_specificity_passed,

    NULLIF(
        ar.result -> 'multi_stage_result' -> 'deep_analysis'
            ->> 'recommend_demand_letter',
        ''
    )::bool                                                      AS recommend_demand_letter,

    -- Error / warning surface
    jsonb_array_length(
        COALESCE(ar.result -> 'warnings', '[]'::jsonb)
    )                                                            AS warning_count,
    jsonb_array_length(
        COALESCE(ar.result -> 'errors', '[]'::jsonb)
    )                                                            AS error_count

FROM analysis_results ar
JOIN cases c ON c.id = ar.case_id
WHERE ar.status = 'completed';

COMMENT ON VIEW letter_quality_signals IS
    'Flattens QA v2 signals from analysis_results.result.generated_letters '
    'for completed analyses. One row per completed analysis_results row. '
    'NULL signals = check not applicable for that letter type.';


-- =============================================================================
-- VIEW: cases_needing_attention
--
-- Surfaces the "imported from Clio, docs uploaded, never analyzed"
-- pattern that was invisible before. One row per case, with counts
-- and last-activity timestamps.
-- =============================================================================

CREATE OR REPLACE VIEW cases_needing_attention AS
SELECT
    c.id                                                         AS case_id,
    c.user_id,
    c.client_name,
    c.status                                                     AS case_status,
    c.jurisdiction,
    c.created_at                                                 AS case_created_at,
    c.updated_at                                                 AS case_updated_at,

    -- Document counts by status
    COUNT(d.id) FILTER (WHERE d.status = 'pending')              AS docs_pending_extraction,
    COUNT(d.id) FILTER (WHERE d.status = 'ready')                AS docs_ready,
    COUNT(d.id) FILTER (WHERE d.status = 'extraction_failed')    AS docs_extraction_failed,
    COUNT(d.id) FILTER (WHERE d.status = 'duplicate')            AS docs_duplicate,
    COUNT(d.id)                                                  AS docs_total,

    -- Job activity
    (SELECT MAX(aj.completed_at)
       FROM analysis_jobs aj WHERE aj.case_id = c.id)            AS last_analysis_completed_at,
    EXISTS (SELECT 1 FROM analysis_jobs aj WHERE aj.case_id = c.id)
                                                                 AS has_ever_been_analyzed,
    EXISTS (SELECT 1 FROM analysis_jobs aj
            WHERE aj.case_id = c.id
              AND aj.status IN ('pending', 'running'))           AS has_active_job

FROM cases c
LEFT JOIN documents d ON d.case_id = c.id
GROUP BY c.id;

COMMENT ON VIEW cases_needing_attention IS
    'One row per case with doc-status counts, last analysis timestamp, '
    'and active-job flag. Filter WHERE NOT has_ever_been_analyzed AND '
    'docs_ready > 0 to find Clio-imported-never-analyzed cases.';


-- =============================================================================
-- RLS — views inherit RLS from underlying tables. analysis_results,
-- cases, and documents already have ownership-gated SELECT policies
-- for authenticated users, and service_role bypasses. No view-level
-- policy needed.
-- =============================================================================
