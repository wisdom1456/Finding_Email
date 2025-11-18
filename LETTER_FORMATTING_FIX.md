# Letter Formatting Fix

## Issue Identified

The generated findings letters had **inconsistent line wrapping** and displayed raw markdown code fences (` ```html ... ``` `) in the final HTML output. This caused:

1. **Literal code display**: The letter content appeared as raw text instead of formatted HTML
2. **Inconsistent line lengths**: Some lines were long, others cut short
3. **Poor readability**: The professional styling wasn't being applied

### Root Cause

The OpenAI API was occasionally wrapping its markdown response in code fences like:

```
```html
<div class="legal-letter">
<p>Dear Client,</p>
...
</div>
```
```

The existing regex patterns in `_clean_markdown_response()` were not robust enough to remove these code fences, especially when they included language specifiers like `html`.

## Changes Made

### 1. Added Code Fence Cleaning to Letter Review Service (`letter_review_service.py`) - **PRIMARY FIX**

**Location**: `src/legal_portal/services/letter_review_service.py` (lines 96-177)

**Added** code fence cleaning to the letter review process. The issue was that the **LetterReviewService** (which runs AFTER the initial letter generation) was receiving HTML with code fences from OpenAI, but wasn't cleaning them.

```python
def review_and_improve_letter(self, draft_letter: str, ...) -> Tuple[str, Optional[ValidationResult]]:
    # ... existing code ...
    
    # 2. Clean any code fences from AI response (NEW!)
    cleaned_content = self._clean_code_fences(reviewed_content)
    
    # 3. Final normalization pass
    final_letter = self._normalize_encoding(cleaned_content)
    
    # 4. Remove editorial notes
    final_letter = self._remove_editorial_notes(final_letter)
```

**Added new method**:
```python
def _clean_code_fences(self, text: str) -> str:
    """Remove markdown code fences from AI response."""
    # Removes ```html, ```markdown, ```, etc.
    # Uses same robust regex patterns as JsonProcessingService
```

**Why this was the issue**: The processing flow is:
1. JsonProcessingService generates initial draft → code fences cleaned ✅
2. **LetterReviewService** reviews and improves draft → AI adds code fences back ❌ (was not being cleaned)
3. DocumentFormatterService wraps in final HTML → code fences remain in output ❌

### 2. Improved Code Fence Cleaning (`json_processing_service.py`) - **PREVENTIVE**

**Location**: `src/legal_portal/services/json_processing_service.py` (lines 302-336)

**Updated** the `_clean_markdown_response()` method with more robust regex patterns:

```python
def _clean_markdown_response(self, response_text: str) -> str:
    """Clean OpenAI response to extract valid Markdown."""
    if not response_text:
        return ""

    cleaned = response_text.strip()
    
    # Remove code fences with language specifiers (```html, ```markdown, etc.)
    cleaned = re.sub(r"^\s*```(?:html|markdown|md)?\s*\n?", "", cleaned, flags=re.MULTILINE)
    
    # Remove closing code fences
    cleaned = re.sub(r"\n?\s*```\s*$", "", cleaned, flags=re.MULTILINE)
    
    # Clean up any remaining stray code fences
    cleaned = re.sub(r"```(?:html|markdown|md)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?\s*```", "", cleaned)
    
    cleaned = cleaned.strip()
    
    # Do NOT remove HTML tags - markdown2 handles mixed content gracefully
    return cleaned
```

**Key improvements**:
- ✅ Handles ` ```html `, ` ```markdown `, ` ```md `, and plain ` ``` ` fences
- ✅ Removes fences with leading/trailing whitespace
- ✅ Multiple passes to catch nested or stray fences
- ✅ No longer strips HTML tags (markdown2 handles this properly)

### 3. Enhanced Text Justification (`document_formatter.py`)

**Location**: `src/legal_portal/services/document_formatter.py` (lines 779-787)

**Updated** paragraph CSS for more consistent text flow:

```css
p {
    margin: 18px 0;
    text-align: justify;           /* NEW: Justified text */
    text-justify: inter-word;      /* NEW: Word spacing control */
    max-width: 85ch;
    hyphens: auto;                 /* NEW: Automatic hyphenation */
    -webkit-hyphens: auto;
    -ms-hyphens: auto;
}
```

**Benefits**:
- ✅ **Justified text alignment**: More consistent line lengths
- ✅ **Smart hyphenation**: Breaks long words appropriately
- ✅ **Professional appearance**: Looks like traditional legal documents

## Testing

Verified the fix with multiple test cases:

1. ✅ HTML code fence with language specifier: ` ```html ... ``` `
2. ✅ Markdown code fence: ` ```markdown ... ``` `
3. ✅ Plain code fence: ` ``` ... ``` `
4. ✅ Code fences with whitespace: `   ```html   ... ```   `
5. ✅ Realistic example matching the provided HTML file
6. ✅ Content without code fences (preserved correctly)

All tests passed successfully.

## Verification Steps

To verify the fix works in production:

1. **Generate a new findings letter** through the application
2. **Download the HTML file**
3. **Check that**:
   - No ` ```html ` or ` ``` ` appears in the file
   - Text is properly formatted with consistent line lengths
   - All paragraphs are justified (not ragged right edges)
   - Professional styling is applied throughout

## Files Modified

1. **`src/legal_portal/services/letter_review_service.py`** ⭐ **PRIMARY FIX**
   - Added `_clean_code_fences()` method
   - Integrated code fence cleaning into review workflow

2. `src/legal_portal/services/json_processing_service.py`
   - Enhanced `_clean_markdown_response()` method (preventive measure)

3. `src/legal_portal/services/document_formatter.py`
   - Updated paragraph CSS with justification and hyphenation

## Technical Details

### Processing Pipeline

The letter generation follows this flow:

```
1. JsonProcessingService generates initial draft
   ↓ _clean_markdown_response() removes code fences ✅
   ↓
2. markdown2.markdown() converts to HTML
   ↓
3. LetterReviewService reviews and improves letter
   ↓ OpenAI returns improved content (sometimes with code fences!)
   ↓ _clean_code_fences() removes them ✅ [NEW FIX]
   ↓
4. CitationTrackingService cleans filename hashes
   ↓
5. DocumentFormatterService wraps in styled HTML [IMPROVED]
   ↓
6. Final HTML saved to file
```

**Key Insight**: The code fences were being added back by the AI in step 3 (review), after the initial cleaning in step 1. We needed to clean them again after the review step.

### Regex Patterns Explained

**Opening fence removal**:
```python
r"^\s*```(?:html|markdown|md)?\s*\n?"
```
- `^\s*` - Match start of line with optional leading whitespace
- ` ``` ` - Match three backticks
- `(?:html|markdown|md)?` - Optionally match language specifier
- `\s*\n?` - Match trailing whitespace and optional newline

**Closing fence removal**:
```python
r"\n?\s*```\s*$"
```
- `\n?` - Optional leading newline
- `\s*` - Optional whitespace
- ` ``` ` - Match three backticks
- `\s*$` - Trailing whitespace and end of string

### CSS Justification

**Why justified text**:
- Legal documents traditionally use justified alignment
- Creates more professional appearance
- Ensures consistent visual density
- Maximum line length still controlled by `max-width: 85ch`

**Browser support**:
- `text-align: justify` - Universal support
- `text-justify: inter-word` - Modern browsers (Chrome, Firefox, Safari)
- `hyphens: auto` - Modern browsers with language support

## Why the Previous Fix Didn't Work

**Initial diagnosis was incomplete**: I first fixed `JsonProcessingService._clean_markdown_response()` which cleaned code fences from the initial draft. However, the letter goes through a **second AI call** in `LetterReviewService` that reviews and improves the draft - and that AI was also returning content with code fences!

**The smoking gun**: When you restarted and generated letter #4, the CSS changes (justified text) were present, proving the code was reloaded. But the code fences persisted because `LetterReviewService` wasn't cleaning them.

**Complete fix required**: Code fence cleaning in BOTH places:
1. ✅ After initial generation (JsonProcessingService) 
2. ✅ After review/improvement (LetterReviewService) ← **This was the missing piece**

## Related Issues

This fix also resolves:
- Inconsistent paragraph wrapping
- Raw HTML/markdown appearing in final output
- Styling not being applied to letter content
- Content appearing as code blocks in downloaded files

## Notes

- The fix is **backward compatible** - existing letters will still work
- No database migrations required
- No changes to API contracts or interfaces
- Linting passes with no errors
- No impact on other services

## Future Improvements

Consider:
1. Adding validation to check for code fences before saving
2. Logging warnings when code fences are detected and removed
3. Adding unit tests for `_clean_markdown_response()` method
4. Monitoring AI responses for unusual formatting patterns

---

**Status**: ✅ Fixed and tested  
**Date**: November 18, 2025  
**Impact**: All future generated letters will have consistent formatting

