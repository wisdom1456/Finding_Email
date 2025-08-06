# Orchestrator Task: Fix Email Generator Prompt System

## 🎯 Mission
Fix the fundamental conflicts in the email generator's prompting system by implementing the AUTHENTIC attorney style throughout, removing conflicting transformations, and aligning all components to produce professional legal letters.

## 📊 Current Situation

### Critical Problem
The email generator has a **dual personality disorder**:
- **Generation Phase:** Uses AUTHENTIC_ATTORNEY_ADVISOR (professional, direct)
- **Post-Processing Phase:** Transforms to CLIENT_CLARITY_ADVISOR (collaborative, warm)
- **Result:** Incoherent output that matches neither real attorneys nor intended style

### Impact
- Letters don't match attorney examples (Devlin, Price, Velasco)
- Artificial "we" language throughout
- Inconsistent tone between sections
- Unprofessional appearance

## 🔧 Implementation Tasks

### Phase 1: Code Cleanup (Priority: CRITICAL)
**File:** `backend_logic/email_generator.py`

1. **Delete conflicting method** (Lines 298-341)
   - Remove entire `_enhance_collaborative_tone()` method
   - This method actively sabotages AUTHENTIC output

2. **Fix post-processing pipeline** (Line 233)
   - Remove call to `_enhance_collaborative_tone()`
   - Keep only essential validations

3. **Simplify formatting** (Lines 343-367)
   - Remove artificial greeting additions (Lines 349-354)
   - Remove artificial closing additions (Lines 364-365)

### Phase 2: Prompt Alignment (Priority: HIGH)
Update all 9 generation methods to use AUTHENTIC style:

1. **`_generate_executive_summary()`**
   - Remove: "collaborative language"
   - Add: Direct professional summary

2. **`_generate_legal_concerns()`**
   - Remove: "collaborative approach"
   - Add: Objective legal analysis

3. **`_generate_media_summary()`**
   - Remove: "we reviewed" language
   - Add: Direct evidence assessment

4. **`_generate_strengths()`**
   - Change: From supportive to analytical

5. **`_generate_challenges()`**
   - Change: From empathetic to objective

6. **`_generate_recommendations()`**
   - Change: To direct action items

7. **`_generate_next_steps()`**
   - Change: To clear procedural steps

8. **`_generate_closing_paragraph()`**
   - Change: To professional sign-off

9. **`_generate_background_summary()`**
   - Already aligned ✓

### Phase 3: Pipeline Simplification (Priority: MEDIUM)
Streamline `_clean_ai_response()` to only:
- Remove markdown artifacts
- Validate Florida citations
- Ensure accessibility formatting
- Apply high-stakes protocol (conditional)

### Phase 4: Testing & Validation (Priority: HIGH)
Create tests matching real attorney patterns:
- **Devlin Pattern:** "1. FACTUAL SUMMARY", bullet points, specific amounts
- **Price Pattern:** Roman numerals, direct analysis
- **Velasco Pattern:** Executive summary, comprehensive sections

## 📋 Task Breakdown for Sub-Modes

### For Code Mode:
1. Backup `email_generator.py`
2. Apply Phase 1 deletions
3. Update all 9 prompts (Phase 2)
4. Simplify pipeline (Phase 3)
5. Create test file

### For Debug Mode:
1. Test against attorney examples
2. Validate Florida citations
3. Check for "we" transformations
4. Verify professional tone

### For Architect Mode:
1. Design fallback strategy
2. Create migration plan
3. Document deprecation strategy

## ✅ Success Criteria

### Must Have:
- ✓ No "we" transformations in output
- ✓ Consistent AUTHENTIC tone throughout
- ✓ Matches attorney example patterns
- ✓ Florida law citations only
- ✓ Professional formatting

### Should Have:
- ✓ Numbered sections with ALL CAPS
- ✓ Bullet points for lists
- ✓ Direct, specific language
- ✓ Clear action items

### Nice to Have:
- ✓ Automated testing suite
- ✓ Performance metrics
- ✓ Rollback capability

## 🚀 Execution Order

1. **Immediate:** Code mode implements Phase 1 & 2
2. **Next:** Debug mode validates changes
3. **Then:** Code mode implements Phase 3
4. **Finally:** Architect mode creates long-term strategy

## ⚠️ Risk Mitigation

- **Backup:** Create `email_generator_backup.py` before changes
- **Testing:** Test each phase independently
- **Rollback:** Keep original methods commented initially
- **Monitoring:** Log generation metrics

## 📊 Expected Outcomes

### Before Fix:
- Inconsistent tone
- Artificial language
- Doesn't match examples
- Unpredictable quality

### After Fix:
- Professional attorney tone
- Matches real examples
- Consistent quality
- Clear, direct communication

## 🎬 Ready for Orchestration

This document provides the complete roadmap for fixing the email generator's prompt system. The orchestrator can now coordinate the implementation across different modes to achieve the AUTHENTIC attorney style throughout the system.

**Estimated Total Time:** 4-6 hours across all modes
**Priority:** CRITICAL - Core functionality broken
**Risk:** LOW - Well-documented changes with backup strategy