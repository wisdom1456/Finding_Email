# Verification Hub Redesign

**Date:** 2026-02-26
**Status:** Approved
**Approach:** Enhanced Cards + Slide-Out Panel (Approach A)

## Goals

1. Move signature verification earlier in the pipeline (from post-analysis to Verification Hub)
2. Give attorneys a triage-first experience with critical summary at top
3. Capture structured attorney input (type overrides, key facts, relevance, notes, relationships) to improve analysis quality
4. Maintain consistency with existing design system (Tailwind + custom brand tokens)

## Selected Features

| # | Feature | Priority |
|---|---------|----------|
| 1 | Attorney Triage Dashboard | High |
| 2 | Inline Signature Verification on Cards | High |
| 3 | Document Type Override | High |
| 4 | Key Facts Confirmation Chips | Medium |
| 5 | Attorney Context Notes | Medium |
| 6 | Relevance / Priority Flagging | Medium |
| 7 | Side-by-Side OCR View | Medium |
| 8 | Document Relationship Linking | Low |
| 10 | Smart Sorting (by attention needed) | High |

Excluded: #9 Guided Review Mode

---

## Section 1: Triage Dashboard

Full-width card at top of Verification Hub, styled `bg-white rounded-2xl shadow-card p-6`.

**Left side — Smart Summary sentence:**
Dynamically generated: "4 documents need attention: 2 missing signatures, 1 low-quality OCR, 1 unclassified type." Uses bold + color for critical items. When all clear: "All 12 documents verified and ready for analysis" in green.

**Right side — Clickable filter chips:**

| Chip | Style | Click Action |
|------|-------|-------------|
| Missing Signatures | `bg-red-50 text-red-700 border-red-200` | Filter to unsigned docs |
| Low OCR Quality | `bg-amber-50 text-amber-700 border-amber-200` | Filter to quality < 5 |
| Needs Type Override | `bg-purple-50 text-purple-700 border-purple-200` | Filter to unclassified |
| Ready | `bg-green-50 text-green-600 border-green-100` | Filter to ready docs |

Chips are toggleable. Multiple can be active. Icon + count + label per chip.

**Progress bar:** Thin horizontal bar showing ready/total progress. Teal `#5AB7A3` fill.

---

## Section 2: Enhanced Document Cards

### Collapsed State (Default)

Single row per card:

```
[Quality Score]  Document Name                [Type Badge]  [Sig Badge]  [Relevance]  [▼]
                 extraction_method • words     Addendum      ✓ Signed     ★ Critical
```

- **Type Badge:** Clickable dropdown to override AI classification. Options: Contract, Addendum, Inspection Report, Disclosure, Correspondence, Invoice/Receipt, Photo/Media, Legal Filing, Other. Shows "overridden" indicator when changed.
- **Signature Badge:** Clickable — opens Signature Review Panel. Uses existing color scheme (emerald/amber/yellow/gray).
- **Relevance Flag:** Star icon, click to cycle: none → Critical Evidence (gold) → Supporting (gray) → Background (outline). Saves immediately.

### Expanded State

Adds below the collapsed row:

**Key Facts Row:** Editable chips from auto-extracted data:
```
📅 Date: 03/15/2024  💰 Amount: $425,000  👤 Parties: Smith, Jones LLC  🏠 Property: 123 Main St
```
Clickable to edit inline. Checkmark when confirmed. Unconfirmed: amber dotted border.

**Attorney Notes:** Text area, collapsed to single line, expands on focus. Saves on blur.

**Document Relationships:** "Link to..." button → dropdown of case documents. Shows existing links as pills: `↔ Contract_Main.pdf (modifies)`. Types: modifies, relates to, supersedes, supports.

**Action Buttons:** Existing View, Re-extract, Edit, Delete buttons.

---

## Section 3: Signature Review Panel

**Trigger:** Click signature badge on any card, or "Missing Signatures" dashboard chip.

**Behavior:** Slide-out panel from right, ~60% width, 300ms transition. Card list stays visible (dimmed). `bg-white shadow-lg border-l border-gray-200`.

### Layout

**Header:** Document name + "Signature Review" + close button.

**PDF Viewer (~70% height):** Renders PDF via existing DocumentPreviewPane. "Jump to signature area" link scrolls to last page (or detected signature page). Zoom controls (+/-/fit).

**Verdict Bar (fixed bottom):**

```
[ ✓ Signed ]     [ ⚠ Concern ]     [ ✗ No Signature ]
  green-600         amber-500           red-600
```

- **Signed:** Saves "signed", closes panel, updates card badge
- **Concern:** Expands text area for notes, saves "unknown" + notes
- **No Signature:** Saves "not_signed", closes panel, updates card badge

**Auto-advance:** After verdict, advances to next document needing review. Shows "2 of 5 remaining" counter.

**Keyboard shortcuts:** S=Signed, C=Concern, N=No Signature, Escape=Close, ←/→=Prev/Next.

---

## Section 4: Smart Sorting

Documents within each triage group sort by attention score (descending):

| Condition | Points |
|-----------|--------|
| Missing expected signature | +50 |
| Low OCR quality (< 5) | +40 |
| No document type detected | +30 |
| No key facts extracted | +20 |
| No attorney notes | +10 |
| Unconfirmed key facts | +5 each |

Subtle label: `"Needs: signature, type"` in `text-xs text-gray-400`.

---

## Section 5: Side-by-Side OCR View

Replaces current 3-tab modal. Uses slide-out panel (~80% width).

```
┌────────────────────────────────────────────────┐
│  Document Name                        [✕]      │
├──────────────────┬─────────────────────────────┤
│  Original PDF    │  Extracted Text             │
│  (scrollable)    │  (scrollable, editable)     │
├──────────────────┴─────────────────────────────┤
│  [Re-extract OCR]  [Edit Text]  [Verify ✓]    │
└────────────────────────────────────────────────┘
```

Independent scrolling. Shows manual_text with "manually edited" badge if applicable.

---

## Section 6: Data Flow & Backend Integration

### Pipeline Change

**Before:** Upload → Verify OCR → Analysis (signature check here)
**After:** Upload → Verify OCR + Signatures + Type + Key Facts → Analysis (uses enriched data)

### API Changes

Existing PATCH `/api/documents/{id}/verify` gains new optional fields:

```python
document_type_override: Optional[str]
relevance_level: Optional[str]  # "critical" | "supporting" | "background"
key_facts: Optional[Dict[str, Any]]
attorney_notes: Optional[str]
document_relationships: Optional[List[Dict]]  # [{related_doc_id, relationship_type}]
```

No new endpoints needed. All saves are optimistic UI updates.

### Analysis Pipeline Reads Enriched Data

`document_registry_service.py` includes:
- Attorney type override (preferred over AI classification)
- Relevance level (weights document importance in findings)
- Confirmed key facts (ground truth for dates, amounts, names)
- Attorney notes (passed as context to findings prompt)
- Relationships (groups related docs)

### Findings Letter Prompt Context

Add to document context block:
- "Attorney has classified this as: [type override]"
- "Attorney relevance: [critical/supporting/background]"
- "Attorney notes: [notes]"
- "Confirmed facts: [key facts]"

---

## Files to Modify

### Frontend
- `frontend/src/lib/components/VerificationHub.svelte` — Major redesign (dashboard, enhanced cards, smart sorting)
- `frontend/src/lib/components/DocumentCard.svelte` — Inline actions (type, signature, relevance, expand/collapse)
- New: `frontend/src/lib/components/SignatureReviewPanel.svelte` — Slide-out signature review
- New: `frontend/src/lib/components/DocumentReviewPanel.svelte` — Side-by-side OCR view
- New: `frontend/src/lib/components/TriageDashboard.svelte` — Top dashboard component
- New: `frontend/src/lib/components/KeyFactsChips.svelte` — Editable fact chips
- New: `frontend/src/lib/components/DocumentRelationships.svelte` — Relationship linking

### Backend
- `src/legal_portal/api/routes/documents.py` — Extend VerifyDocumentRequest with new fields, store in metadata
- `src/legal_portal/services/document_registry_service.py` — Include enriched attorney data in registry
- `src/legal_portal/services/json_processing_service.py` — Pass attorney context to findings prompt
- `src/legal_portal/prompts/findings_letter_prompt.txt` — Document context block additions

### Design Constraints
- All styling must use existing Tailwind tokens and brand colors
- Font: Raleway (headings), Montserrat (body)
- Primary accent: `#5AB7A3` teal
- Cards: `rounded-2xl shadow-card`
- Buttons: existing `.btn-primary`, `.btn-secondary`, `.btn-danger` patterns
- Badges: existing pill-shaped pattern with status color variants
- Use `/frontend-design` skill for implementation to ensure design quality
