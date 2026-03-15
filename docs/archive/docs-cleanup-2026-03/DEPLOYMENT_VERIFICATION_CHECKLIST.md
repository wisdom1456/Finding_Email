# Deployment Verification Checklist

Manual steps to run after deploying the production remediation fixes.
These verify the fixes against real infrastructure.

---

## 1. Analysis Save (Schema Mismatch Fix)

- [ ] Navigate to a case with extracted documents
- [ ] Click "Analyze Case" / start streaming analysis
- [ ] Wait for streaming to complete
- [ ] **Verify**: Analysis saves successfully (no red error banner)
- [ ] **Verify**: Results tab loads with document summaries and quality report
- [ ] **Verify**: Server logs show NO `42703` errors or `document_type`/`quality_score` column references

```bash
# Or via curl:
curl -s -X POST "${API_URL}/api/analysis/stream/${CASE_ID}/save" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"content": "# Test Analysis\n\nVerification test."}' | python3 -m json.tool
# Expected: 200 OK
```

## 2. EML Extraction (Error Handling Fix)

- [ ] Upload a `.eml` file to any case
- [ ] Trigger extraction (auto or manual)
- [ ] **Verify**: Document status becomes `ready` (not `extraction_failed`)
- [ ] **Verify**: Extracted text contains email body content
- [ ] **Verify**: No 500 error in server logs

## 3. Supabase 503 Retry

- [ ] Open browser DevTools > Console
- [ ] Navigate between pages (cases list > case detail > back)
- [ ] **Verify**: All data loads normally
- [ ] **Simulated test**: In Supabase SQL editor, run `COMMENT ON TABLE cases IS 'trigger cache refresh';` to force a schema cache rebuild, then immediately load the app
- [ ] **Verify**: The app recovers after a brief retry (no permanent error state)

## 4. Save Error UX

- [ ] Start analysis on a case
- [ ] While streaming, block the save URL in DevTools Network tab
- [ ] Wait for streaming to complete
- [ ] **Verify**: Red banner appears: "Analysis completed but couldn't be saved."
- [ ] **Verify**: "Retry Save" button is visible
- [ ] Unblock the URL, click "Retry Save"
- [ ] **Verify**: Banner disappears, save succeeds

## 5. Click Handler Performance

- [ ] Open DevTools > Performance tab
- [ ] Click "Analyze Case" button
- [ ] **Verify**: No long tasks >100ms in the main thread
- [ ] **Verify**: Streaming panel appears immediately (no 100ms+ delay)
- [ ] **Verify**: Documents are already loaded from cache (no blocking fetch)

## 6. End-to-End Smoke Test

Full pipeline on the previously-failing case:

- [ ] Navigate to case `bfabcc6a-c6cf-47c0-ba23-a355c7136aec`
- [ ] Verify documents list loads
- [ ] Start analysis
- [ ] Wait for completion
- [ ] **Verify**: Analysis saves (no error banner)
- [ ] Navigate to results
- [ ] **Verify**: Results page loads with document summaries, quality report, and analysis content
