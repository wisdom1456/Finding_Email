# Implementation Plan: AUTHENTIC Attorney Style
## Aligning Email Generator with Real Attorney Communications

### Decision: AUTHENTIC Attorney Style ✓
Based on user selection, we will implement the direct, professional tone that matches real attorney examples (Devlin, Price, Velasco).

---

## Phase 1: Remove Conflicting Transformations

### 1.1 Disable CLIENT_CLARITY_ADVISOR Transformations
**File:** `backend_logic/email_generator.py`

#### Remove from `_apply_final_presentation_improvements()` (Line 222-239):
```python
# DELETE Line 233:
# content = self._enhance_collaborative_tone(content)  # REMOVE THIS
```

#### Delete entire `_enhance_collaborative_tone()` method (Lines 298-341):
```python
# DELETE ENTIRE METHOD - Lines 298-341
# This method contradicts AUTHENTIC_ATTORNEY_ADVISOR
```

#### Modify `_apply_final_formatting()` (Lines 343-367):
```python
def _apply_final_formatting(self, content: str) -> str:
    """Apply minimal formatting for professional presentation."""
    if not content:
        return content

    # Only ensure proper paragraph structure
    content = re.sub(r'([.!?])\s+([A-Z])', r'\1</p>\n<p>\2', content)

    # Remove artificial greeting/closing additions (Lines 349-354, 364-365)
    # Let the prompts handle greetings and closings

    return content
```

---

## Phase 2: Align ALL Prompts with AUTHENTIC Style

### 2.1 Fix Executive Summary Prompt (Lines 796-816)
```python
def _generate_executive_summary(self, analysis: CaseAnalysisResult, persona: str) -> str:
    prompt = f"""
    Draft a concise, professional executive summary (2-3 sentences) for a legal findings letter.
    Include the greeting 'Good afternoon {analysis.intake_analysis.client_name},' or similar.

    Requirements:
    - Use direct, professional language without artificial collaboration
    - State findings and recommendations based on Florida law
    - Be matter-of-fact without overselling the case
    - Format as HTML paragraphs using `<p>` tags
    - Match the tone of professional attorney communications

    Case Context:
    {analysis.model_dump_json(indent=2)}

    Generate only the HTML-formatted executive summary.
    """
    result = self._make_openai_request(prompt, persona)
    return result or "<p>Good afternoon, I have completed my analysis of your legal matter.</p>"
```

### 2.2 Fix Legal Concerns Prompt (Lines 839-860)
```python
def _generate_legal_concerns(self, analysis: CaseAnalysisResult, persona: str) -> str:
    prompt = f"""
    Identify the key legal concerns using direct, professional language.

    Requirements:
    - Use clear, accessible language without legal jargon
    - List main legal issues using bullet points
    - State findings directly without collaborative "we" language
    - Format with `<ul>` and `<li>` tags
    - Focus exclusively on Florida law
    - Be objective and matter-of-fact

    Case Context:
    {analysis.model_dump_json(indent=2)}

    Generate the key legal concerns using bullet points.
    """
    result = self._make_openai_request(prompt, persona)
    return result or "<p>Key legal considerations in this matter include:</p>"
```

### 2.3 Update ALL Other Section Prompts
Apply same pattern to:
- `_generate_background_summary()` ✓ (already aligned)
- `_generate_media_summary()` - Remove collaborative language
- `_generate_strengths()` - Use direct assessment language
- `_generate_challenges()` - Be objective, not supportive
- `_generate_recommendations()` - Direct recommendations
- `_generate_next_steps()` - Clear action items
- `_generate_closing_paragraph()` - Professional sign-off
- `_generate_video_analysis_appendix()` - Technical, direct analysis

---

## Phase 3: Update Persona Constants

### 3.1 Ensure Consistency (Lines 25-96)
```python
# Keep AUTHENTIC_ATTORNEY_ADVISOR as primary
AUTHENTIC_ATTORNEY_ADVISOR = f"""
You are a senior litigation attorney writing a professional legal analysis letter
that mirrors the style of real attorney communications.

{CORE_DIRECTIVES}

**MANDATORY STYLE REQUIREMENTS:**
1. **Professional Greeting:** "Good afternoon [Name]" or "Dear [Name]"
2. **Numbered Sections:** Use ALL CAPS headers (1. FACTUAL SUMMARY, etc.)
3. **Direct Language:** No artificial collaboration or "we" statements
4. **Bullet Points:** Organize key information clearly
5. **Florida Law Only:** Reference only Florida statutes and case law
6. **Matter-of-Fact Tone:** Present analysis objectively
7. **Single Professional Closing:** One clear sign-off
"""

# Set all personas to AUTHENTIC
CLIENT_DIRECTED_PERSONA = AUTHENTIC_ATTORNEY_ADVISOR
CONTINUING_LETTER_PERSONA = CONTINUING_ATTORNEY_ADVISOR
```

---

## Phase 4: Simplify Post-Processing Pipeline

### 4.1 Streamline `_clean_ai_response()` (Lines 369-414)
```python
def _clean_ai_response(self, content: str, is_counter_intuitive: bool = False) -> str:
    """Clean AI responses with minimal transformation."""
    if not content:
        return ""

    # Remove markdown artifacts
    cleaned = re.sub(r'^```[a-zA-Z]*\n?', '', content, flags=re.MULTILINE)
    cleaned = re.sub(r'```$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', cleaned)
    cleaned = re.sub(r'\*(.*?)\*', r'<em>\1</em>', cleaned)

    # Fix HTML structure
    cleaned = re.sub(r'<p>\s*<p>', '<p>', cleaned)
    cleaned = re.sub(r'</p>\s*</p>', '</p>', cleaned)
    cleaned = re.sub(r'<p>\s*</p>', '', cleaned)

    # Apply only necessary validations
    cleaned = self._validate_florida_citations(cleaned)
    cleaned = self._ensure_accessibility_formatting(cleaned)

    if is_counter_intuitive:
        cleaned = self._apply_high_stakes_advice_protocol(cleaned)

    # DO NOT apply collaborative transformations
    # DO NOT add artificial greetings/closings

    return cleaned.strip()
```

---

## Phase 5: Testing Strategy

### 5.1 Validation Against Real Examples
Test output should match:

#### Devlin Pattern:
- Greeting: "Good afternoon Mr. Devlin and Ms. Bell,"
- Sections: "1. FACTUAL SUMMARY", "2. IMPLIED WARRANTY"
- Tone: Direct with specific amounts ($128,355.77)
- No "we" language except where natural

#### Price Pattern:
- Roman numerals: "I. Background", "II. Review"
- Matter-of-fact analysis
- Direct recommendations

#### Velasco Pattern:
- Professional executive summary
- Comprehensive appendix
- Clear, direct legal analysis

### 5.2 Test Cases
1. Generate letter with Devlin case data → Verify numbered sections
2. Generate letter with Price case data → Verify Roman numerals
3. Generate letter with Velasco case data → Verify executive summary
4. Check for absence of collaborative "we" transformations
5. Verify Florida law citations only
6. Confirm professional greetings and closings

---

## Phase 6: Rollback Plan

If issues arise:
1. Keep backup of current `email_generator.py` as `email_generator_backup.py`
2. Test in isolated environment first
3. Gradual rollout: Test with one case type before full deployment
4. Monitor output quality metrics

---

## Implementation Checklist

- [ ] Remove `_enhance_collaborative_tone()` method
- [ ] Update `_apply_final_presentation_improvements()`
- [ ] Simplify `_apply_final_formatting()`
- [ ] Fix executive summary prompt
- [ ] Fix legal concerns prompt
- [ ] Update all other section prompts
- [ ] Align persona constants
- [ ] Simplify `_clean_ai_response()`
- [ ] Create test cases
- [ ] Validate against attorney examples
- [ ] Document changes
- [ ] Deploy and monitor

---

## Expected Outcome

After implementation:
- ✓ Consistent AUTHENTIC attorney tone throughout
- ✓ Matches real attorney communication style
- ✓ No conflicting transformations
- ✓ Professional, direct, matter-of-fact output
- ✓ Proper numbered sections with ALL CAPS headers
- ✓ Florida law focus maintained
- ✓ Clean, predictable HTML output
