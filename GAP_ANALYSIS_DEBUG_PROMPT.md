# Gap Analysis Feature - Debug & Implementation Prompt

## Context

You are debugging and completing the implementation of a **Gap Analysis feature** for a legal document analysis application. This feature identifies missing documents, factual contradictions, timeline gaps, and unverifiable claims in legal cases.

## Application Architecture

### Tech Stack
- **Backend**: Python/FastAPI, deployed on Vercel (serverless)
- **Frontend**: SvelteKit
- **Database**: Supabase (PostgreSQL)
- **AI**: OpenAI GPT-5.2 for analysis

### Key Components
```
src/legal_portal/
├── api/routes/analysis.py          # API endpoints for analysis
├── services/
│   ├── multi_stage_analyzer.py     # Multi-stage analysis orchestrator
│   ├── gap_analysis_service.py     # Gap detection service (NEW)
│   └── main_processor.py           # Main document processor
└── core/data_models.py              # Pydantic models

frontend/src/
├── routes/app/cases/[id]/results/+page.svelte  # Results UI
└── lib/components/GapAnalysisPanel.svelte      # Gap display UI (NEW)
```

## Feature Implementation Summary

### What Was Built

1. **Backend Data Models** (`src/legal_portal/core/data_models.py`)
   - `GapSeverity` enum: critical, high, medium, low
   - `GapCategory` enum: missing_document, factual_contradiction, timeline_gap, unverifiable_claim, incomplete_info
   - `GapItem` model: Individual gap with title, description, recommendations
   - `GapAnalysisResult` model: Complete analysis with completeness score
   - Updated `MultiStageAnalysisResult` to include `gap_analysis` field

2. **Gap Analysis Service** (`src/legal_portal/services/gap_analysis_service.py`)
   - `GapAnalysisService.analyze_gaps()` method
   - Uses GPT-5.2 with specialized prompt to detect:
     - Missing documents (referenced but not provided)
     - Factual contradictions across documents
     - Timeline gaps and missing dates
     - Unverifiable claims without evidence
   - Returns structured `GapAnalysisResult`

3. **Multi-Stage Analyzer Integration** (`src/legal_portal/services/multi_stage_analyzer.py`)
   - Added Stage 3.5 in `analyze_case()` method
   - Runs gap analysis after deep analysis (Stage 3)
   - Initializes `GapAnalysisService` in `__init__`
   - Added extensive logging: `[INIT]`, `[STAGE:3.5]`, `[GAP_SERVICE]`

4. **Frontend Components**
   - TypeScript types in `frontend/src/lib/types.ts`
   - `GapAnalysisPanel.svelte`: Displays gaps with filtering, severity badges
   - Updated results page with "Gaps" tab

5. **Debug Endpoint** (`src/legal_portal/api/routes/debug_gap.py`)
   - `/api/debug/gap-analysis/{case_id}` - Check if gap analysis exists

## The Problem

### Symptoms
- ✅ Multi-stage analysis runs successfully
- ✅ Gap service is created: `[INIT] GapAnalysisService created: True`
- ❌ Gap analysis does NOT appear in results
- ❌ No "Gaps" tab in UI
- ❌ `multi_stage_result` contains `["issue_map", "fact_matrix", "deep_analysis", "letter_structure"]` but NO `gap_analysis`

### Root Cause Discovered

**The application has TWO analysis code paths:**

1. **Standard Multi-Stage Analysis** (`analyze_case()`)
   - Goes through Stages 1-4 sequentially
   - Stage 3.5 (gap analysis) was added here ✅
   - Used in background processing via `/api/analysis/start` → `process_case_background`

2. **Streaming Analysis** (`analyze_streaming()`) ⚠️ **THIS IS WHAT'S BEING USED**
   - Single GPT-5.2 streaming call for speed
   - Generates markdown output in real-time
   - Results saved via `/api/analysis/stream/{case_id}/save`
   - Builds `multi_stage_result` from parsed streaming response
   - **Gap analysis was NOT added to this path initially**

**Log evidence:**
```
[STREAM] Starting streaming analysis | jurisdiction=Florida docs=25
[STREAM] Saved streaming analysis for case X | structured_data=yes
```

The gap service was being initialized but never executed because the code path went through `analyze_streaming()`, not `analyze_case()`.

## Solution Implemented

Added gap analysis to the **streaming analysis save endpoint** at `src/legal_portal/api/routes/analysis.py` line ~2076:

```python
# After multi_stage_result is built from streaming response
# Before saving to database

if multi_stage_result:
    try:
        # Create gap service
        from legal_portal.services.gap_analysis_service import GapAnalysisService
        from legal_portal.utils.openai_client import OpenAIClient

        openai_client = OpenAIClient()
        gap_service = GapAnalysisService(openai_client=openai_client)

        # Convert dicts to Pydantic models
        fact_matrix = FactMatrix(**multi_stage_result["fact_matrix"])
        issue_map = LegalIssueMap(**multi_stage_result["issue_map"])
        deep_analysis = DeepAnalysis(**multi_stage_result["deep_analysis"])

        # Run gap analysis
        gap_result = await gap_service.analyze_gaps(...)

        # Add to result
        multi_stage_result["gap_analysis"] = gap_result.model_dump(mode="json")

    except Exception as gap_err:
        logger.error(f"Gap analysis failed: {gap_err}")
        multi_stage_result["gap_analysis"] = None
```

## Current Status

### What's Been Done
1. ✅ Gap analysis added to streaming save endpoint
2. ✅ Code committed and pushed to main branch
3. ✅ Debug endpoint created for verification
4. ✅ Extensive logging added throughout
5. ⏳ Awaiting Vercel deployment and testing

### What Needs Verification

After deployment, test:

1. **Run new analysis** on any case
2. **Check debug endpoint**: `GET /api/debug/gap-analysis/{case_id}`
   - Should show `"has_gap_analysis": true`
   - Should include gap data with counts
3. **Check results UI**: Should show "Gaps" tab with badge if critical/high gaps exist
4. **Check Vercel logs**: Should show `[STREAM] Gap analysis complete: X gaps found`

## Your Task

1. **Review the implementation** in these files:
   - `src/legal_portal/api/routes/analysis.py` (streaming save endpoint, ~line 2076)
   - `src/legal_portal/services/gap_analysis_service.py`
   - `src/legal_portal/services/multi_stage_analyzer.py`
   - `frontend/src/routes/app/cases/[id]/results/+page.svelte`
   - `frontend/src/lib/components/GapAnalysisPanel.svelte`

2. **Identify any issues** with:
   - Async/await handling in streaming save (currently uses `asyncio.to_thread` + `asyncio.run`)
   - Pydantic model conversion from dicts
   - Error handling and fallbacks
   - JSON serialization of gap analysis result

3. **Verify the solution** works by:
   - Running a test analysis
   - Checking the debug endpoint response
   - Confirming gap_analysis appears in database

4. **Fix any remaining issues** such as:
   - Async execution problems in serverless environment
   - Model conversion errors
   - Missing fields in gap analysis result
   - Frontend not displaying gaps tab

## Potential Issues to Watch For

### 1. Async/Await in Streaming Save
The current implementation uses:
```python
gap_result = await asyncio.to_thread(
    lambda: asyncio.run(gap_service.analyze_gaps(...))
)
```

This is **nested async execution** which may cause issues. Consider:
- Making the streaming save endpoint properly await gap_service.analyze_gaps()
- Or making analyze_gaps() synchronous if it's called from sync context

### 2. Model Conversion
Converting dict → Pydantic models may fail if:
- Field names don't match exactly
- Nested models aren't converted properly
- Optional fields are missing

### 3. Serverless Timeout
Gap analysis adds ~10-15 seconds. Vercel functions have timeouts:
- Hobby: 10s
- Pro: 60s
- Ensure function doesn't timeout

### 4. Missing intake_content
Streaming save uses `request.content` (markdown analysis) as proxy for intake:
```python
intake_content=request.content[:5000]
```

This is the analysis output, not the original intake form. May need to fetch actual intake from database.

## Debug Checklist

- [ ] Check Vercel deployment logs for `[STREAM] Running gap analysis`
- [ ] Verify no errors in `[STREAM] Gap analysis failed:`
- [ ] Confirm gap_analysis appears in database via debug endpoint
- [ ] Test that Gaps tab appears in UI
- [ ] Verify gap data is complete (not null/empty)
- [ ] Check gap analysis prompt is generating valid JSON
- [ ] Confirm no timeout issues on Vercel

## Test Case IDs
- Case ID used in testing: `b60ea6bf-e33c-42ef-8566-60fa0af441fd`
- Recent analysis: `ae234904-91a4-4b2e-b2a9-a515501de268`

## Expected Debug Endpoint Output

**Before fix:**
```json
{
  "has_gap_analysis": false,
  "multi_stage_keys": ["issue_map", "fact_matrix", "deep_analysis", "letter_structure"],
  "gap_analysis_null_reason": "Field exists but is null/undefined"
}
```

**After fix (target):**
```json
{
  "has_gap_analysis": true,
  "multi_stage_keys": ["issue_map", "fact_matrix", "deep_analysis", "letter_structure", "gap_analysis"],
  "gap_analysis": {
    "total_gaps": 5,
    "critical_count": 2,
    "high_count": 1,
    "completeness_score": 72.5
  }
}
```

## Files Modified in This Feature

### Backend
- `src/legal_portal/core/data_models.py` - Added gap models
- `src/legal_portal/services/gap_analysis_service.py` - NEW
- `src/legal_portal/services/multi_stage_analyzer.py` - Added Stage 3.5
- `src/legal_portal/api/routes/analysis.py` - Added gap to streaming save
- `src/legal_portal/api/routes/debug_gap.py` - NEW debug endpoint
- `src/legal_portal/api/main.py` - Registered debug router

### Frontend
- `frontend/src/lib/types.ts` - Gap analysis types
- `frontend/src/lib/components/GapAnalysisPanel.svelte` - NEW
- `frontend/src/routes/app/cases/[id]/results/+page.svelte` - Added Gaps tab

## Key Functions to Review

1. **`GapAnalysisService.analyze_gaps()`** - Main gap detection logic
2. **`MultiStageAnalyzer.analyze_case()`** - Stage 3.5 integration (standard path)
3. **`save_streaming_analysis()`** - Gap analysis for streaming path (the one being used)
4. **Frontend gap data loading** - Check if `gapAnalysis` derived state is working

## Success Criteria

- [ ] Gap analysis runs on every new analysis
- [ ] Results appear in database with gap_analysis field populated
- [ ] UI shows "Gaps" tab with badge for critical/high gaps
- [ ] Gap panel displays filtered, categorized gaps
- [ ] No errors or timeouts in Vercel logs
- [ ] Performance acceptable (~10-15s added to analysis time)

## Next Steps

1. Deploy latest code to Vercel
2. Run fresh analysis on test case
3. Call debug endpoint and verify has_gap_analysis: true
4. Check UI for Gaps tab
5. Review any errors in logs
6. Fix any async/model conversion issues found
7. Optimize if needed (caching, parallel execution, etc.)

## Additional Context

The user is testing on a Vercel staging deployment. They can provide:
- Vercel deployment URLs
- Log CSV exports
- Debug endpoint responses
- Screenshots of UI

Use the debug endpoint liberally to check state between changes. All commits go to main branch and auto-deploy to Vercel.
