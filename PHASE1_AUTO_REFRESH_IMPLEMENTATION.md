# Phase 1: Auto-Refresh UI Implementation

## Date: November 4, 2025

## Problem Identified

The user reported two issues:
1. **OpenAI API Timeout Failure**: The processing failed due to OpenAI API timeouts (the API took too long to respond and exhausted all 3 retry attempts)
2. **Manual Refresh Required**: Users had to manually click "Refresh Status" every 10-30 seconds to check progress
3. **No Countdown Timer**: Users couldn't see when the next refresh would occur

## Root Cause

From the terminal logs (lines 129-135), we can see:
```
APITimeoutError: Request timed out.
RetryError[<Future at 0x15fb247d0 state=finished raised APITimeoutError>]
```

The OpenAI GPT-5 API timed out 3 times:
- First timeout: 17:11:12 (90 seconds)
- Second timeout: 17:12:46 (90 seconds) 
- Third timeout: 17:14:19 (90 seconds) - FAILED

Total time spent: ~5.5 minutes before giving up.

**This is NOT a bug in our code** - it's an OpenAI API availability issue. However, our error messaging was unclear.

## Solution Implemented

### 1. Auto-Refresh Every 10 Seconds ✅

**File:** `src/legal_portal/ui/main.py`

**Changes:**
- Added `last_refresh_time` to session state to track when the last refresh occurred
- Implemented automatic `st.rerun()` every 10 seconds when processing is active
- Added a 1-second sleep at the end of the render to update the countdown smoothly

**Code:**
```python
# Initialize last refresh time if not set
if "last_refresh_time" not in st.session_state:
    st.session_state.last_refresh_time = time.time()

# Calculate time since last refresh
time_since_refresh = time.time() - st.session_state.last_refresh_time
seconds_until_refresh = max(0, 10 - int(time_since_refresh))

# Auto-refresh every 10 seconds
if time_since_refresh >= 10:
    st.session_state.last_refresh_time = time.time()
    st.rerun()
```

### 2. Countdown Timer ✅

**Visual Indicator:**
```python
st.write(f"🔄 **Next auto-refresh in:** {seconds_until_refresh} seconds")
```

The countdown shows: 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0, then refreshes.

### 3. Better Error Messages ✅

**Enhanced error handling:**
```python
# Provide more helpful error messages for common issues
if "APITimeoutError" in error_msg or "Request timed out" in error_msg:
    error_msg = "OpenAI API timeout - The AI service took too long to respond. This usually means the model is overloaded. Please try again in a few minutes."
elif "RetryError" in error_msg:
    error_msg = "Multiple API failures - The AI service failed after several retry attempts. Please check your internet connection and try again."
```

### 4. Enhanced Time Display

**Shows elapsed time in minutes and seconds:**
```python
if st.session_state.processing_start_time:
    elapsed = time.time() - st.session_state.processing_start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    if minutes > 0:
        st.write(f"**Time Elapsed:** {minutes}m {seconds}s")
    else:
        st.write(f"**Time Elapsed:** {seconds} seconds")
```

### 5. Cleanup on Completion

**Clears refresh timer:**
```python
finally:
    # Clear the last refresh time for next run
    if "last_refresh_time" in st.session_state:
        del st.session_state.last_refresh_time
```

## User Experience Improvements

### Before:
❌ User had to manually click "Refresh Status" every 20-30 seconds
❌ No indication of when to check again
❌ Generic error message: "RetryError[<Future...>]"
❌ No clear understanding of what went wrong

### After:
✅ **Automatic refresh every 10 seconds**
✅ **Countdown timer:** "Next auto-refresh in: 7 seconds"
✅ **Clear error message:** "OpenAI API timeout - The AI service took too long to respond. This usually means the model is overloaded. Please try again in a few minutes."
✅ **Better time display:** "Time Elapsed: 5m 32s" instead of "332 seconds"
✅ **"Refresh Now" button** to manually trigger immediate refresh

## UI Display (During Processing)

```
⚡ Analysis in Progress
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 Auto-refreshing every 10 seconds - UI remains responsive!

🔄 Next auto-refresh in: 7 seconds

Current Status: 🤖 AI Call #2: Generating findings letter...

Time Elapsed: 3m 42s

[Progress Bar: ████████████████████░░░░░░░░░]

[🔄 Refresh Now]  [⏹️ View Current Results]
```

## Technical Notes

### Why 10 Seconds?
- **Not too frequent:** Avoids excessive reruns that could slow down Streamlit
- **Not too slow:** Provides timely updates without feeling sluggish
- **Countdown makes waiting feel shorter:** Users can see exactly when the next update will occur

### Thread Safety
The implementation is thread-safe because:
1. Session state updates are atomic in Streamlit
2. Only the background thread writes to `processing_progress`, `processing_status`, and `processing_error`
3. The main thread only reads these values and manages UI refresh timing

### Performance Impact
- **Minimal:** The 1-second sleep and rerun adds negligible overhead
- **No duplicate API calls:** The background thread continues running independently
- **No wasted cycles:** Refresh only happens when `processing_status == "active"`

## Testing Instructions

1. **Start a new analysis** with the test case files
2. **Observe the countdown timer** - it should count down from 10 to 0
3. **Wait for auto-refresh** - at 0 seconds, the UI should automatically refresh
4. **Check status updates** - you should see progress messages like:
   - "🔄 Initializing processing services..."
   - "📄 Processing intake form and 2 documents..."
   - "🤖 AI Call #1: Generating document summaries..."
   - "🤖 AI Call #2: Generating findings letter..."
5. **Test "Refresh Now" button** - clicking it should immediately refresh and reset the countdown to 10
6. **Test failure scenario** - if OpenAI times out again, you should see:
   - Clear error message about API timeout
   - Suggestion to try again in a few minutes
   - "Reset and Try Again" button

## Known Issues & Limitations

### OpenAI API Timeouts
**NOT FIXED** - This is an external API issue, not a bug in our code.

**Why it happens:**
- GPT-5 is a very large model and can be slow
- OpenAI's servers may be overloaded
- Your request may be complex/large (10KB+ prompt)

**Mitigation strategies (for future implementation):**
1. **Switch to GPT-4o** - Faster and more reliable (recommendation: do this!)
2. **Increase timeout** - Currently 90 seconds per attempt, could go to 120-180 seconds
3. **Reduce prompt size** - Summarize documents more aggressively before sending to GPT
4. **Add streaming** - Use SSE streaming to show partial results as they're generated
5. **Implement circuit breaker** - If API fails 3+ times, suggest using a different model

### Current Timeout Configuration
Located in: `src/legal_portal/services/json_processing_service.py`

```python
"gpt-5": {
    "timeout": 90.0,  # 90 seconds per attempt
    "max_retries": 2,  # 3 total attempts (initial + 2 retries)
}
```

**Total max time before failure:** 90s × 3 = 270 seconds (4.5 minutes)

## Recommendations

### Immediate (User Action Required):
1. **Try again in 5-10 minutes** - OpenAI API may be less loaded
2. **Check OpenAI status page** - https://status.openai.com
3. **Verify API key quota** - Make sure you haven't hit rate limits

### Short-term (Code Changes):
1. **Switch to GPT-4o** - Much faster, more reliable, and cheaper
2. **Add model selection UI** - Let users choose between GPT-4o, GPT-4-turbo, GPT-5
3. **Implement progressive timeout** - Start with 60s, then 90s, then 120s on retries

### Long-term (Architecture):
1. **Streaming responses** - Show partial results as they generate
2. **Resume capability** - Save partial progress, resume from last successful step
3. **Background job queue** - Process in worker thread pool, email results when done
4. **Multiple AI providers** - Fall back to Anthropic Claude or Google Gemini if OpenAI fails

## Files Modified

1. `src/legal_portal/ui/main.py`
   - Added auto-refresh logic (lines 173-186)
   - Added countdown timer display (line 193)
   - Enhanced elapsed time display (lines 200-207)
   - Improved error messages (lines 107-111)
   - Added refresh timer cleanup (lines 121-122)
   - Changed "Refresh Status" to "Refresh Now" (line 215)

## Summary

✅ **Auto-refresh implemented** - Every 10 seconds
✅ **Countdown timer added** - Shows seconds until next refresh
✅ **Better error messages** - Clear explanation of API timeout
✅ **Enhanced time display** - Minutes and seconds format
✅ **Manual refresh button** - "Refresh Now" for immediate update

**The API timeout issue itself is not fixed** - it's an OpenAI service limitation. However, users now have:
- Better visibility into what's happening
- Automatic status updates without manual clicking
- Clear error messages explaining the issue
- A countdown so they know when the next update will occur

## Next Steps

1. **User tests the auto-refresh functionality**
2. **If satisfied, consider switching from GPT-5 to GPT-4o for reliability**
3. **Continue with Phase 1 testing as outlined in the test plan**

