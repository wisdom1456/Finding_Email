# Bug Fix: OpenAIClient Error on Vercel

## Issue Date
December 13, 2025 - 08:55:34 UTC

## Problem
Letter generation on Vercel was failing with error:
```
Letter polishing failed: 'OpenAIClient' object has no attribute 'chat'
```

## Root Cause
The `LetterPolisher` class in `src/legal_portal/utils/letter_polish.py` was trying to call the OpenAI SDK directly:

```python
response = self.client.chat.completions.create(...)  # ❌ Wrong
polished_letter = response.choices[0].message.content.strip()
```

However, `self.client` is our custom `OpenAIClient` wrapper class, not the raw OpenAI SDK client. Our wrapper doesn't expose the `.chat` attribute.

## Solution
Changed the code to use the wrapper's public API method:

```python
response = self.client.create_chat_completion(...)  # ✅ Correct
polished_letter = response["content"].strip()
```

## Files Changed
- `src/legal_portal/utils/letter_polish.py` (lines 155-169)

## Testing
After deploying this fix to Vercel:

1. **Test Letter Generation:**
   - Go to a case with completed analysis
   - Click "Generate Letters" tab
   - Click "Generate Letter" for findings or demand letter
   - Should complete without the "polishing failed" error

2. **Test Chat Feature:**
   - Go to "Case Chat" tab
   - Type a question and press Enter
   - Should receive a response (not "load failed")

## Deployment Steps
```bash
# Commit the fix
git add src/legal_portal/utils/letter_polish.py
git commit -m "fix: Use OpenAIClient wrapper method instead of direct SDK access"
git push origin main

# Vercel will auto-deploy
# Wait 2-3 minutes for deployment to complete
```

## What This Fixes
✅ Letter polishing pass now works correctly  
✅ Findings letters generate without errors  
✅ Demand letters generate without errors  
✅ No more AttributeError in Vercel logs

## Related Issues
This bug only affected Vercel because the error handling would silently fall back to the unpolished letter. Users would still get letters, but they wouldn't have the final formatting polish pass applied.

## Monitoring
After deployment, check Vercel function logs for:
- ✅ No more `'OpenAIClient' object has no attribute 'chat'` errors
- ✅ Letter polish pass completing successfully
- ✅ Log messages showing "Formatting polish applied successfully"

## Chat "Load Failed" Issue
The chat issue you mentioned is a **separate problem**. The logs don't show any `/api/analysis/chat` calls yet, so either:

1. You haven't tested chat yet after this logs export
2. Chat is failing on the client side before reaching the server
3. Chat requires a case with `multi_stage_result` data (older analyses won't work)

### To Test Chat:
1. Ensure you're using a case with recent analysis (post multi-stage update)
2. Open browser DevTools (F12) → Network tab
3. Try sending a chat message
4. Check if the request reaches `/api/analysis/chat`
5. Look at the response status code and error message

If chat is still failing after this fix, the error will be different and we can debug from there.

## Prevention
Consider adding a type check or documentation comment in `LetterPolisher.__init__()` to clarify that it expects an `OpenAIClient` wrapper instance, not the raw OpenAI SDK client.

```python
def __init__(self, openai_client):
    """Initialize the polisher.
    
    Args:
    ----
        openai_client: OpenAIClient wrapper instance (from legal_portal.utils.openai_client)
                       NOT the raw OpenAI SDK client
    """
    self.client = openai_client
    self.formatting_prompt = self._load_formatting_prompt()
```

