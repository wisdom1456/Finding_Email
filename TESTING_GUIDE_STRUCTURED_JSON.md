# Testing Guide: Structured JSON Workflow

**Date:** November 4, 2025  
**Purpose:** Validate the structured JSON workflow implementation

---

## 🎯 Testing Objectives

1. Verify structured JSON extraction works correctly
2. Validate quality assessment integration
3. Confirm enhanced letter content (citations, sources, balanced analysis)
4. Test comprehensive letter review functionality
5. Ensure conditional debug logging works

---

## 🧪 Test 1: Basic Workflow Validation

### Setup
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails

# Enable debug logging
export LOG_LEVEL=DEBUG

# Start application
streamlit run run_app.py
```

### Test Steps
1. **Upload Test Documents:**
   - Navigate to the UI
   - Upload an intake form (e.g., from `cost_sessions/` or `test_data/Tyler, Austin/`)
   - Upload 2-3 case documents (mix of PDF and images)
   - Click "Start Analysis"

2. **Monitor Terminal Logs:**
   Look for these key indicators:
   ```
   ✅ Successfully parsed X structured document summaries
   Quality assessment complete: high/medium/low confidence
   AI Call #1: Generating structured document summaries...
   AI Call #2: Generating findings letter from structured data...
   AI Call #3: Comprehensive letter review and formatting...
   Letter review complete: XXXX -> YYYY chars
   ```

3. **Check for JSON Parsing:**
   - No errors like "❌ Failed to parse JSON response"
   - No "JSON parsing failed" exceptions
   - Structured summaries count matches number of documents

### Expected Results
- ✅ All 3 AI calls complete successfully
- ✅ Structured JSON parsed without errors
- ✅ Quality validation runs and reports confidence level
- ✅ Letter generated and reviewed
- ✅ Processing completes with status "completed"

---

## 🧪 Test 2: Letter Quality Inspection

### Test Steps
1. **Open Generated Letter:**
   - After processing completes, view the generated letter in UI
   - Save a copy for detailed review

2. **Check Key Provisions Section:**
   ```
   Expected Format:
   1. **Florida Statute § XXX.XX(X) - Provision Name**
      * Plain English: [explanation]
      * Application to Your Case: [specific application with names/dates/amounts]
      * Source: [Document name, Section/Page]
   ```
   
   **Verify:**
   - [ ] Specific statute numbers with subsections (not vague "Florida law")
   - [ ] Each provision has a "Source:" citation
   - [ ] Application section uses specific facts from the case

3. **Check Analysis Section:**
   ```
   Expected Structure:
   - Favorable Facts (with document sources)
   - Challenges (honest assessment)
   - Realistic Outcome (settlement/litigation timeline)
   - Financial Impact (documented damages, potential recovery)
   ```
   
   **Verify:**
   - [ ] All 4 elements are present
   - [ ] Favorable facts cite source documents
   - [ ] Financial amounts match case documents
   - [ ] Balanced (not overly optimistic)

4. **Check Next Steps Section:**
   ```
   Expected Format:
   1. **Action Name (Within X days)**
      - What to do: [specific action]
      - Why it matters: [legal reason]
      - Risk if delayed: [consequence]
   ```
   
   **Verify:**
   - [ ] Each step has a specific timeframe (not "soon" or "immediately")
   - [ ] Each step explains consequence of delay
   - [ ] Each step provides legal/strategic reason

5. **Check Source Citations:**
   **Verify throughout letter:**
   - [ ] Major dates cited with source (e.g., "per Disclosure Form, Question 3")
   - [ ] Dollar amounts cited with source (e.g., "$590,000 purchase price (Source: Contract)")
   - [ ] Party names used consistently
   - [ ] No vague references like "the document" or "a contract"

### Expected Results
- ✅ Letter contains specific statute citations with subsections
- ✅ Every major fact has a source document reference
- ✅ Analysis includes all 4 required elements
- ✅ Next Steps have timeframes and consequences
- ✅ Professional, consistent formatting

---

## 🧪 Test 3: Quality Validation Testing

### Test Scenario: Upload Low-Quality Image
1. **Upload a Poor-Quality Image:**
   - Use a blurry photo or low-resolution scan
   - Process it along with good-quality documents

2. **Check Terminal Logs:**
   ```
   Expected:
   Quality assessment complete: medium confidence, 1/3 low quality
   ⚠️ DOCUMENTS WITH QUALITY ISSUES:
   - filename.png: Score 4.5/10
     Issues: High character repetition detected, possibly due to OCR errors
   ```

3. **Check Generated Letter:**
   - Look for cautious language like "based on available information"
   - Check for quality warnings in Analysis section
   - Verify low-quality docs flagged appropriately

### Expected Results
- ✅ Quality validator detects low-quality extraction
- ✅ Quality context passed to AI calls
- ✅ Letter includes appropriate caveats for low-quality sources
- ✅ Warnings logged but processing continues

---

## 🧪 Test 4: Intake-Only Processing

### Test Steps
1. **Upload Only Intake Form:**
   - Do NOT upload any case documents
   - Click "Start Analysis"

2. **Monitor Logs:**
   ```
   Expected:
   No case documents provided - processing intake form only.
   Quality context: "No documents to validate (intake-only processing)"
   AI Call #1: Generating structured document summaries...
   ✅ Successfully parsed 0 structured document summaries
   (or intake-only analysis)
   ```

3. **Check Generated Letter:**
   - Should have content based on intake form
   - Should note missing documents in Analysis
   - Should recommend gathering specific documents

### Expected Results
- ✅ Processing completes without case documents
- ✅ Letter generated from intake information only
- ✅ Letter notes information gaps appropriately
- ✅ No errors or crashes

---

## 🧪 Test 5: Conditional Logging Verification

### Test Steps
1. **Run with DEBUG Logging:**
   ```bash
   export LOG_LEVEL=DEBUG
   streamlit run run_app.py
   ```
   - Process a test case
   - Check logs for "CONTEXT CHECK" messages
   - Should see: "CONTEXT CHECK - Intake preview:", etc.

2. **Run without DEBUG Logging:**
   ```bash
   unset LOG_LEVEL
   streamlit run run_app.py
   ```
   - Process the same test case
   - Check logs - should NOT see "CONTEXT CHECK" messages
   - Logs should be clean and professional

### Expected Results
- ✅ CONTEXT CHECK logs appear only when `LOG_LEVEL=DEBUG`
- ✅ Production logs are clean (no debug spam)
- ✅ Important info logs still appear (AI call progress, errors)

---

## 🧪 Test 6: Error Handling

### Test Scenario: Trigger JSON Parsing Failure
This is hard to simulate, but if it happens:

1. **Expected Behavior:**
   ```
   ❌ Structured summarization failed: JSON parsing failed: [error details]
   ERROR: Processing failed: Document summarization failed - cannot generate letter
   ```

2. **Recovery:**
   - Error should be logged clearly
   - Processing should stop gracefully (not crash)
   - User should see clear error message in UI
   - No partial/corrupt letter should be generated

---

## 📊 Test Results Template

Use this template to document your testing results:

```markdown
## Test Results: [Date]

### Test 1: Basic Workflow
- Documents tested: [list files]
- Structured JSON parsing: ✅ / ❌
- Quality validation: ✅ / ❌
- All 3 AI calls completed: ✅ / ❌
- Notes: [any issues or observations]

### Test 2: Letter Quality
- Statute citations specific: ✅ / ❌
- Source citations present: ✅ / ❌
- Analysis has 4 elements: ✅ / ❌
- Next Steps have timeframes: ✅ / ❌
- Overall quality (1-10): [score]
- Notes: [specific improvements or issues]

### Test 3: Quality Validation
- Low-quality docs detected: ✅ / ❌
- Appropriate caveats added: ✅ / ❌
- Notes: [observations]

### Test 4: Intake-Only
- Processing completed: ✅ / ❌
- Letter quality: ✅ / ❌
- Notes: [observations]

### Test 5: Conditional Logging
- DEBUG logs visible when enabled: ✅ / ❌
- No DEBUG logs in production: ✅ / ❌
- Notes: [observations]

### Test 6: Error Handling
- Errors handled gracefully: ✅ / ❌ / N/A
- Notes: [if errors occurred]

---

## Summary
[Overall assessment of implementation]
[Any issues to address]
[Recommended next steps]
```

---

## 🔧 Troubleshooting Guide

### Issue: "❌ Failed to parse JSON response"
**Cause:** GPT-4o returned malformed JSON or wrapped in unexpected format

**Solution:**
1. Check terminal logs for "Raw response:" (first 500 chars shown)
2. Look for markdown code blocks that weren't stripped
3. If consistent, adjust prompt in `main_processor.py` line ~301-353

### Issue: Letter missing source citations
**Cause:** AI Call #2 not using JSON fields correctly, or AI Call #3 not adding them

**Solution:**
1. Check if structured JSON contains `source_document` fields (view logs)
2. If JSON has sources but letter doesn't, AI Call #2 or #3 not following instructions
3. Review and strengthen prompt in `findings_letter_prompt.txt` or `letter_review_service.py`

### Issue: Quality validation too strict/lenient
**Cause:** Thresholds in `DocumentQualityValidator` not calibrated

**Solution:**
1. Edit `src/legal_portal/services/document_quality_validator.py`
2. Adjust `min_content_length` (default 50) and `min_word_count` (default 10)
3. Modify scoring logic in `validate_document_quality()` method

### Issue: Processing very slow (>5 minutes)
**Cause:** 3 AI calls + quality validation adds processing time

**Solution:**
1. Check individual AI call durations in logs
2. Consider reducing max_tokens if responses are verbose
3. May need to optimize prompts to reduce input token count
4. Quality validation should be fast (<1 second) - if not, investigate

### Issue: CONTEXT CHECK logs always appear
**Cause:** Environment variable not set correctly

**Solution:**
```bash
# Ensure LOG_LEVEL is unset for production
unset LOG_LEVEL
echo $LOG_LEVEL  # Should be empty

# Or explicitly set to INFO
export LOG_LEVEL=INFO
```

---

## 📈 Performance Benchmarks

Track these metrics during testing:

| Metric | Target | Actual | Notes |
|--------|--------|--------|-------|
| Total processing time | <3 min | ___ | 3 AI calls + quality validation |
| JSON parsing success rate | 100% | ___% | Should never fail with GPT-4o |
| Quality validation time | <2 sec | ___ | Should be very fast |
| Letter completeness score | 9/10+ | ___/10 | All required elements present |
| Source citation coverage | 100% | ___% | All major facts cited |

---

## ✅ Sign-Off Checklist

Before considering implementation complete:

- [ ] All 6 tests passed successfully
- [ ] Letter quality meets attorney standards
- [ ] No critical errors in any test scenario
- [ ] Performance is acceptable (<5 minutes total)
- [ ] Documentation is complete and accurate
- [ ] Test results template filled out
- [ ] Any issues documented with solutions

---

**Ready to test!** Start with Test 1 and work through systematically. 🧪

