# Verification Hub — Manual Validation Checklist

**Purpose:** Validate AI-driven and integration scenarios that cannot be fully covered by automated Playwright tests.

Run this checklist after any significant changes to:
- `src/legal_portal/services/json_processing_service.py`
- `src/legal_portal/prompts/findings_letter_prompt.txt`
- `src/legal_portal/services/document_registry_service.py`
- Any frontend Verification Hub component

---

## Prerequisites

```bash
# Terminal 1: Backend in Vercel simulation mode
make debug

# Terminal 2: Frontend dev server
make frontend

# Open browser at http://localhost:5173
```

---

## 1. Triage Dashboard

| Step | Action | Expected Result | Pass? |
|------|--------|-----------------|-------|
| 1.1 | Open a case with 3+ documents of varying quality | TriageDashboard renders with summary line | |
| 1.2 | Verify progress bar shows `0 of N documents ready` initially | Progress bar visible and shows correct count | |
| 1.3 | Click "Missing Signatures" chip (if visible) | Document list filters to only unsigned docs | |
| 1.4 | Click chip again to deactivate | Full document list restored | |
| 1.5 | Click "Needs Classification" chip (if visible) | Shows only docs without a type label | |
| 1.6 | Click "Ready" chip | Shows only docs with `status=ready` | |
| 1.7 | Verify chip `aria-pressed` attribute toggles in browser devtools | `aria-pressed="true"` when active | |

---

## 2. DocumentCard Inline Enrichment

| Step | Action | Expected Result | Pass? |
|------|--------|-----------------|-------|
| 2.1 | Click the type override dropdown on a document card | Dropdown opens with document type options | |
| 2.2 | Select "Contract" | Selection is saved; reload confirms persistence | |
| 2.3 | Click the star/relevance button | Relevance cycles: none → critical → supporting → background | |
| 2.4 | Set relevance to "critical" | Star button title reflects new level | |
| 2.5 | Expand a card via chevron | Attorney notes textarea and key facts section reveal | |
| 2.6 | Type notes in the attorney notes field; blur | Notes are saved (verify via document refresh) | |
| 2.7 | Collapse the card | Expanded content hides | |
| 2.8 | Add a key fact chip (if `key_facts` present) | Chip appears in amber/unconfirmed state | |
| 2.9 | Click confirm button on a fact chip | Chip turns green/confirmed | |

---

## 3. Signature Review Panel

| Step | Action | Expected Result | Pass? |
|------|--------|-----------------|-------|
| 3.1 | Click a signature status badge on a document card | SignatureReviewPanel opens (65% width slide-out) | |
| 3.2 | Verify panel title is "Signature Review" | `h2#slide-out-panel-title` = "Signature Review" | |
| 3.3 | Verify document name and "X of Y" progress shown | Sub-header shows filename and `1 of N` | |
| 3.4 | Click "Load PDF Preview" button | PDF loads inline; "Jump to signature" hint appears | |
| 3.5 | Dismiss the hint via "Dismiss" button | Hint banner disappears | |
| 3.6 | Click "✓ Signed" | Verdict saved; panel auto-advances to next doc (or closes if last) | |
| 3.7 | Re-open panel and click "⚠ Concern" | Concern notes textarea appears with "Save Concern" button | |
| 3.8 | Type concern notes and click "Save Concern" | Verdict `unknown` saved with notes; advances | |
| 3.9 | Re-open panel; click "⚠ Concern" then "Cancel" | Notes textarea disappears; verdict not saved | |
| 3.10 | Re-open panel; press keyboard `S` | Signed verdict saved (same as button click) | |
| 3.11 | Re-open panel; press keyboard `N` | Not-signed verdict saved | |
| 3.12 | Re-open panel; press keyboard `C` | Concern textarea activates | |
| 3.13 | Press `←` / `→` arrow keys | Navigates to previous/next document in queue | |
| 3.14 | Press `Escape` | Panel closes | |
| 3.15 | Click overlay (dark backdrop) outside panel | Panel closes | |

---

## 4. Document Review Panel (OCR Side-by-Side)

| Step | Action | Expected Result | Pass? |
|------|--------|-----------------|-------|
| 4.1 | Click "Preview" or similar action on a document card | DocumentReviewPanel opens (82% width) | |
| 4.2 | Verify left column shows "Original Document" header | Left pane has PDF/image preview area | |
| 4.3 | Verify right column shows "Extracted Text" header | Right pane shows extracted text or `(No text extracted)` | |
| 4.4 | For a document with `manual_text`, verify "Manually Edited" badge in right pane header | Amber badge visible | |
| 4.5 | Click "Re-extract OCR" button | API call triggered; check network tab for PATCH/POST | |
| 4.6 | Click "Edit Text" button | Text editing mode activates (or modal opens) | |
| 4.7 | Click "✓ Verify" button | Document verified; panel closes | |
| 4.8 | Press `Escape` | Panel closes | |

---

## 5. AI Context Injection — Findings Letter Accuracy

This is the most critical validation. It ensures that attorney enrichment data flows through to the AI prompt.

### Setup
1. Open a case that has been fully analyzed at least once.
2. Locate a document that was classified as "Unknown" or had low confidence.
3. Use the Verification Hub to:
   - Override its type to a specific value (e.g., "Medical Record")
   - Set relevance to "critical"
   - Add a note: "Primary evidence of injury — do not downplay"
   - Confirm a key fact: `date: 2024-01-15`

### Validation Steps

| Step | Action | Expected Result | Pass? |
|------|--------|-----------------|-------|
| 5.1 | After enriching the document, trigger a new analysis run | Analysis starts successfully | |
| 5.2 | Open the generated findings letter | Letter loads without errors | |
| 5.3 | Search the letter for the attorney-provided document type | Type override reflected in document reference | |
| 5.4 | Verify the "critical" document receives prominent treatment | Document discussed in key findings section | |
| 5.5 | Search for the confirmed date (`2024-01-15`) | Date appears as a verified fact | |
| 5.6 | Check that the attorney note phrase "do not downplay" influenced tone | Section referencing this document uses strong language | |
| 5.7 | Check backend logs for attorney enrichment in the prompt context | `Attorney Input:` appears in document context string in logs | |

### Verification via Backend Log Check

```bash
# While analysis runs, tail the backend logs and search for enrichment:
make debug 2>&1 | grep -i "attorney"
```

Expected log output snippet:
```
Attorney Input: Attorney classified as: Medical Record | Attorney relevance: critical | Attorney notes: Primary evidence...
```

---

## 6. Sorting — Attention Score

| Step | Action | Expected Result | Pass? |
|------|--------|-----------------|-------|
| 6.1 | In Triage View, verify documents with `signature_expected=true` and unsigned status appear at top | Documents with signatures needed listed first | |
| 6.2 | Verify low-OCR documents (`quality_score < 5`) appear above well-extracted ones | Low quality docs sorted higher within triage group | |
| 6.3 | After marking all signatures as "Signed", verify those docs move to a lower group | Signed docs no longer in "Needs Immediate Attention" | |

---

## 7. Deployment Safety

```bash
# Always run before pushing to production
make verify    # Check requirements consistency between local and Vercel
make pre-push  # Full verification + API smoke test
```

| Check | Command | Expected Result | Pass? |
|-------|---------|-----------------|-------|
| 7.1 | Requirements consistency | `make verify` | No version mismatches | |
| 7.2 | API smoke test | `make pre-push` | All checks pass | |
| 7.3 | Backend unit tests | `pytest tests/unit/ tests/api/ -v` | All pass | |
| 7.4 | Frontend unit tests | `cd frontend && npm run test:run` | All pass | |

---

## Sign-off

After completing all sections above:

- [ ] All critical path items (sections 3, 5) verified manually
- [ ] No regressions in document enrichment persistence
- [ ] `make pre-push` passes clean
- [ ] Findings letter accurately reflects attorney overrides

**Validated by:** _______________  **Date:** _______________
