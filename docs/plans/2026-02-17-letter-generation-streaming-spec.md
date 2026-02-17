# Letter Generation Streaming and Quality Contract - Implementation Spec

Created: 2026-02-17  
Status: Draft for implementation

## 1. Purpose

Define a cohesive, runtime-safe architecture for client-facing letter generation that:

1. Improves quality consistency across findings and recommendation letters.
2. Preserves strong streaming UX.
3. Reduces timeout risk in Vercel serverless execution.
4. Adds measurable acceptance metrics (TTFT, timeout rate, lint pass rate, user-visible latency).

This spec is implementation-oriented and includes endpoint contracts, SSE event schemas, frontend state transitions, and SLO targets.

## 2. Scope

In scope:

1. Findings letter streaming and non-stream generation flow.
2. Recommendation letter generation flow.
3. Post-generation quality lint and conditional repair.
4. Observability and acceptance criteria.

Out of scope:

1. Full legal analysis pipeline redesign.
2. Corpus ingestion changes.
3. Demand-letter legal content redesign (only runtime/stream compatibility items if needed).

## 3. Current Constraints and Baseline

System constraints:

1. Vercel max function duration is 300s (`vercel.json`).
2. Findings generation currently uses large prompt/context and high verbosity.
3. Non-stream findings path includes a second AI polish call.
4. Stream findings path emits token-only SSE payloads (`token`, `done`) and does not persist streamed output.
5. Frontend stream parser reads chunk lines directly and needs robust carry-buffer handling for split SSE lines.

Risk summary:

1. Multiple AI passes can exceed practical serverless budgets.
2. Output verbosity causes longer model time and larger responses.
3. Inconsistent stream/non-stream quality outcomes can create UX trust issues.

## 4. Target Architecture

### 4.1 High-level flow

Use a bounded, phase-driven generation contract:

1. Phase A: Build prompt context (bounded size).
2. Phase B: Draft generation (streaming for findings).
3. Phase C: Deterministic lint validation.
4. Phase D: Conditional repair (only when lint fails and budget remains).
5. Phase E: Finalize and persist final letter.

### 4.2 Runtime budget policy

Per letter request budget target:

1. Hard ceiling: 300s (platform).
2. Internal budget: 240s total (60s reserve).
3. Phase budgets:
4. A context build: 20s max.
5. B draft generation: 160s max.
6. C lint: 20s max.
7. D conditional repair: 30s max.
8. E persistence/finalization: 10s max.

Behavior when budget pressure occurs:

1. Skip repair if remaining budget < 30s.
2. Return best available draft with lint metadata.
3. Always persist best available output.

## 5. API Contract

## 5.1 Findings stream endpoint

Endpoint (existing):

1. `GET /api/analysis/{analysis_id}/letter/stream`

Query params:

1. `force_generation` (bool, existing).
2. `mode` (optional): `default | strict_quality`.
3. `schema_version` (optional): `1 | 2`, default `2`.

Auth:

1. Bearer token required (existing behavior).

Response:

1. `text/event-stream`.

Backward compatibility:

1. Continue emitting `token` and `done` fields for legacy frontend compatibility.
2. Add structured `event` field and envelope fields under schema v2.

## 5.2 Non-stream findings endpoint

Endpoint (existing):

1. `POST /api/analysis/generate-letter` with `letter_type=findings`.

Additions:

1. Include `quality_report` in JSON response.
2. Include `generation_metrics` in JSON response.

## 5.3 Recommendation letter endpoint

Endpoint (existing):

1. `POST /api/analysis/generate-recommendation-letter`.

Additions:

1. Optional progressive mode via SSE in a new endpoint:
2. `GET /api/analysis/{analysis_id}/recommendation-letter/stream?letter_type=...`
3. Keep existing POST for compatibility.
4. Standardize `quality_report` and `generation_metrics` in final payload.

## 5.4 SSE event schema (v2)

Transport format:

1. Standard SSE frame: `data: {json}\n\n`.

Envelope fields (all events):

```json
{
  "schema_version": 2,
  "request_id": "uuid",
  "analysis_id": "uuid",
  "event": "phase|token|heartbeat|quality|final|done|error",
  "timestamp": "2026-02-17T12:34:56.123Z"
}
```

Event payloads:

1. Phase event:
```json
{
  "event": "phase",
  "phase": "context_build|draft_generation|lint_validation|repair|finalizing",
  "message": "Building context",
  "percent": 22
}
```

2. Token event:
```json
{
  "event": "token",
  "token": "Under ",
  "stream": "draft",
  "seq": 141
}
```

3. Heartbeat event:
```json
{
  "event": "heartbeat",
  "phase": "draft_generation",
  "elapsed_ms": 18342
}
```

4. Quality event:
```json
{
  "event": "quality",
  "lint": {
    "passed": false,
    "score": 0.82,
    "violations": ["missing_required_section", "word_count_high"]
  },
  "repair": {
    "attempted": true,
    "applied": true,
    "reason": "lint_failed"
  }
}
```

5. Final event:
```json
{
  "event": "final",
  "content_markdown": "Subject: ...",
  "content_html": "<html>...",
  "quality_report": {
    "lint_passed": true,
    "violations": [],
    "word_count": 812
  },
  "generation_metrics": {
    "ttft_ms": 2450,
    "total_latency_ms": 28420,
    "model_calls": 1,
    "timed_out": false
  }
}
```

6. Done event:
```json
{
  "event": "done",
  "done": true
}
```

7. Error event:
```json
{
  "event": "error",
  "code": "GENERATION_TIMEOUT|MODEL_ERROR|VALIDATION_ERROR",
  "message": "Generation exceeded time budget",
  "recoverable": true
}
```

Legacy compatibility events:

1. `{"token":"..."}` remains supported.
2. `{"done":true}` remains supported.

## 6. Backend State and Persistence Contract

For all generation paths:

1. Persist final output into `analysis_results.result.generated_letters`.
2. Persist `quality_report` and `generation_metrics` adjacent to letter entry.
3. On stream cancellation, persist best partial draft only if minimum content threshold met.

Suggested generated letter record shape:

```json
{
  "generated_letters": {
    "findings": "<html>...",
    "findings_meta": {
      "schema_version": 2,
      "quality_report": {
        "lint_passed": true,
        "violations": [],
        "word_count": 804
      },
      "generation_metrics": {
        "ttft_ms": 2300,
        "total_latency_ms": 26200,
        "timed_out": false,
        "model_calls": 1,
        "repair_applied": false
      }
    }
  }
}
```

## 7. Frontend State Model

### 7.1 Findings letter generation states

Replace binary `generatingFindings` with explicit state machine:

1. `idle`
2. `connecting`
3. `context_build`
4. `draft_generation`
5. `lint_validation`
6. `repair`
7. `finalizing`
8. `complete`
9. `error`
10. `cancelled`

### 7.2 State transitions

Rules:

1. `idle -> connecting` when request starts.
2. `connecting -> context_build` on first phase event.
3. `context_build -> draft_generation` on phase event.
4. `draft_generation -> lint_validation` on phase event.
5. `lint_validation -> repair` only if lint failed and repair attempted.
6. `lint_validation|repair -> finalizing` once final content is being prepared.
7. `finalizing -> complete` on `done`.
8. Any active state -> `error` on `error` event.
9. Any active state -> `cancelled` on user abort.

### 7.3 Streaming rendering behavior

1. Render draft incrementally during `token` events.
2. On `final` event, replace draft with canonical final content.
3. Show non-blocking badge if repair changed output: `Quality pass applied`.
4. Keep previous successful letter visible until first token or final arrives to avoid blank flash.

### 7.4 Parser robustness requirements

1. Implement carry-buffer line assembly for chunked SSE frames.
2. Parse only complete `data:` frames.
3. Ignore malformed partial lines and continue.
4. Maintain sequence checks for token events (`seq`) to detect drops.

## 8. Quality Lint Contract

Lint categories:

1. `structure`: required sections and ordering.
2. `brevity`: total and per-section word ceilings.
3. `style`: banned internal terms and boilerplate repetition.
4. `urgency_language`: forbid hard-coded day-count-from-today phrasing in client output.
5. `actionability`: recommendation and action-item completeness.

Quality report schema:

```json
{
  "lint_passed": true,
  "score": 0.93,
  "violations": [],
  "word_count": 788,
  "section_counts": {
    "opening": 88,
    "core_issue": 59,
    "facts": 122,
    "legal_theories": 284,
    "timing_risk": 73,
    "strategy": 108,
    "action_items": 54
  }
}
```

## 9. Observability and Metrics

## 9.1 Required backend metrics

Per request capture:

1. `request_id`
2. `analysis_id`
3. `letter_type`
4. `streaming` (bool)
5. `ttft_ms`
6. `total_latency_ms`
7. `model_calls`
8. `repair_attempted`
9. `repair_applied`
10. `timeout` (bool)
11. `error_code` (nullable)
12. `lint_passed`
13. `lint_score`

## 9.2 Metric definitions

1. TTFT (time-to-first-token):
2. Timestamp of request accepted -> first `token` event emitted.

3. Timeout rate:
4. `(requests that ended with platform timeout or internal budget timeout) / total generation requests`.

5. Lint pass rate:
6. `(requests where lint_passed=true before optional repair) / total requests`.

7. User-visible latency:
8. Request start -> `final` event received in frontend.

## 9.3 Acceptance targets (30-day rolling)

Findings stream:

1. TTFT p50 <= 3.0s.
2. TTFT p95 <= 8.0s.
3. User-visible latency p50 <= 35s.
4. User-visible latency p95 <= 90s.
5. Timeout rate <= 1.0%.
6. Error rate (non-timeout) <= 1.5%.
7. Lint pass rate pre-repair >= 85%.
8. Lint pass rate post-repair >= 97%.

Recommendation letter generation:

1. User-visible latency p50 <= 25s.
2. User-visible latency p95 <= 70s.
3. Timeout rate <= 1.0%.
4. Lint pass rate post-repair >= 97%.

## 10. Rollout Plan

Phase 1: Event schema and parser hardening.

1. Add schema v2 events with legacy compatibility.
2. Add frontend carry-buffer parser.
3. Add persistence for streamed findings final output.

Phase 2: Runtime budgeting and lower verbosity.

1. Reduce default verbosity for findings stream.
2. Add phase budgets and skip-repair rules under budget pressure.
3. Add generation metrics to responses and logs.

Phase 3: Lint and conditional repair.

1. Add deterministic lint pass.
2. Add optional repair only on lint failure.
3. Expose quality report in UI.

Phase 4: Recommendation stream parity.

1. Add optional streaming endpoint for recommendation letters.
2. Reuse same event schema and metrics.

Feature flags:

1. `LETTER_STREAM_SCHEMA_V2`.
2. `LETTER_QUALITY_LINT_ENABLED`.
3. `LETTER_CONDITIONAL_REPAIR_ENABLED`.
4. `RECOMMENDATION_STREAM_ENABLED`.

## 11. Testing Plan

Backend tests:

1. SSE schema contract tests for each event type.
2. Budget-timeout behavior tests.
3. Persistence tests for streamed final content.
4. Lint rule unit tests with pass/fail fixtures.

Frontend tests:

1. Stream parser chunk-split and malformed-line resilience tests.
2. State machine transition tests.
3. Draft-to-final replacement behavior tests.
4. Abort/retry/cancel handling tests.

Integration tests:

1. End-to-end stream completion under normal load.
2. Simulated slow model response with heartbeat continuity.
3. Simulated repair path and final replacement.
4. Simulated timeout fallback path and user-visible messaging.

## 12. Risks and Mitigations

Risk: Added quality steps increase latency.

1. Mitigation: Conditional repair only.
2. Mitigation: Strict phase budgets.
3. Mitigation: Lower verbosity and prompt size caps.

Risk: Event schema change breaks existing UI.

1. Mitigation: Maintain `token` and `done` compatibility fields.
2. Mitigation: Versioned schema and staged rollout.

Risk: Stream disconnects lose generated output.

1. Mitigation: Persist final/best output server-side.
2. Mitigation: Add recoverable error messaging and retry affordance.

## 13. Implementation Checklist

1. Add schema v2 SSE envelope and event emitters.
2. Add generation metrics collection and persistence.
3. Add deterministic lint service and report format.
4. Add conditional repair with budget guard.
5. Persist streamed findings final output and metadata.
6. Harden frontend SSE parser with carry buffer.
7. Introduce frontend generation state machine.
8. Show phase status and quality badges in UI.
9. Add automated tests for backend and frontend contracts.
10. Enable feature flags in staged rollout and track SLOs.
