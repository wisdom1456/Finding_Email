# Graceful Error Handling for SSE Timeouts

## Problem

The application uses Server-Sent Events (SSE) for real-time progress updates during long-running operations like Clio document imports and AI analysis. However, on Vercel's serverless platform:

1. **SSE connections can timeout** after the maximum function duration (now 10 minutes)
2. **Long-running operations** (especially Clio imports with many documents) may take longer than the timeout
3. **Users see "stalled" progress** when the SSE stream dies mid-operation
4. **No graceful fallback** when SSE fails or times out

## Solution

Implemented a comprehensive graceful degradation strategy with **automatic polling fallback**:

### 1. SSE Inactivity Detection (`sseClient.ts`)

- **Inactivity Timer**: Monitors SSE stream for activity (5-minute timeout)
- **Keep-alive Tracking**: Resets timer on any message (including pings)
- **Automatic Timeout**: Triggers error handler if no messages for 5 minutes
- **Clean Disconnect**: Properly closes connections and clears timers

```typescript
// Key features:
- inactivityTimeout = 300000  // 5 minutes
- Tracks lastMessageTime
- Resets timer on each message
- Triggers SSE_TIMEOUT error when inactive
```

### 2. Polling Fallback (`pollingClient.ts`)

- **HTTP Polling**: Falls back to REST API when SSE fails
- **Configurable Frequency**: Polls every 3 seconds
- **Max Duration**: 6 minutes of polling (120 attempts)
- **Same Interface**: Uses identical progress event structure as SSE
- **Graceful Degradation**: Automatically activated when SSE times out

```typescript
// Polling configuration:
- pollFrequency = 3000ms (3 seconds)
- maxPollAttempts = 120 (6 minutes total)
- Uses /status endpoints for current state
```

### 3. Unified Progress Store (`progressStore.ts`)

- **Automatic Fallback**: Seamlessly switches from SSE to polling
- **Transparent to UI**: Same API regardless of transport method
- **Status URL Support**: Requires polling endpoint URL
- **Token Management**: Passes authentication for polling requests

```typescript
// Fallback logic:
1. Try SSE connection first
2. If SSE times out → switch to polling
3. If SSE not supported → use polling immediately
4. Continue until operation completes or times out
```

### 4. Backend Status Endpoints (`progress.py`)

New polling endpoints added:

- `GET /api/progress/analysis/{analysis_id}/status`
- `GET /api/progress/clio-import/{import_id}/status`

These endpoints:
- Return current progress state
- Don't block (instant response)
- Use latest cached status from progress manager

### 5. Progress Manager State Storage (`progress_manager.py`)

- **Stores Latest Status**: Keeps last progress update in memory
- **Polling Support**: Provides instant access to current state
- **Cleanup**: Removes stale status on channel cleanup

## User Experience

### Before (Stalled State)
```
Loading Clio documents...
[Progress bar at 60%]
... silence for 5+ minutes ...
User confused, refreshes page, loses progress
```

### After (Graceful Degradation)
```
Loading Clio documents...
[Progress bar at 60%]
Stream timeout, switching to polling mode...
[Progress continues updating every 3 seconds]
[Eventually completes or shows meaningful error]
```

## Usage

### Frontend Components

All components using progress updates have been updated:

1. **ClioMatterSearch.svelte**:
   ```typescript
   const statusUrl = `${apiUrl}/api/progress/clio-import/${result.import_id}/status`;
   progressStore.connect(sseUrl, onComplete, statusUrl, session.access_token);
   ```

2. **cases/[id]/+page.svelte** (Analysis):
   ```typescript
   const statusUrl = `${getApiUrl()}/api/progress/analysis/${analysisId}/status`;
   progressStore.connect(sseUrl, onComplete, statusUrl, session.access_token);
   ```

### Backend (No Changes Required)

The progress manager automatically stores latest status for polling endpoints. Existing `publish_progress` calls work for both SSE and polling.

## Configuration

### Timeouts
- **SSE Inactivity**: 5 minutes (`inactivityTimeout` in `sseClient.ts`)
- **Polling Duration**: 6 minutes (`maxPollAttempts` in `pollingClient.ts`)
- **Poll Frequency**: 3 seconds (`pollFrequency` in `pollingClient.ts`)
- **Vercel Function**: 10 minutes (`maxDuration` in `vercel.json`)

### Adjusting Timeouts

To change timeouts, edit the respective files:

```typescript
// sseClient.ts - Increase SSE timeout to 8 minutes
private inactivityTimeout = 480000;  // 8 minutes

// pollingClient.ts - Poll for 10 minutes
private maxPollAttempts = 200;  // 200 * 3s = 10 minutes
```

## Error Messages

Users will see clear status messages:

- **SSE Timeout**: "Stream timeout, switching to polling mode..."
- **Polling Timeout**: "POLLING_TIMEOUT: Maximum polling duration exceeded"
- **Connection Failure**: "SSE_CONNECTION_FAILED" → auto-fallback to polling
- **Not Supported**: "SSE_NOT_SUPPORTED" → uses polling immediately

## Benefits

1. **No Silent Failures**: Users always see progress or meaningful errors
2. **Automatic Recovery**: Seamless fallback without user intervention
3. **Extended Operations**: Can handle tasks longer than SSE timeout
4. **Better UX**: Clear messaging about what's happening
5. **Resilient**: Works even if SSE is blocked/unsupported

## Testing

To test the fallback behavior:

1. **Simulate Timeout**: Set `inactivityTimeout = 10000` (10 seconds) in `sseClient.ts`
2. **Trigger Long Operation**: Import a large Clio matter with many documents
3. **Observe Fallback**: Should see message about switching to polling mode
4. **Verify Completion**: Operation should complete via polling

## Future Improvements

1. **Configurable Timeouts**: Move timeouts to environment variables
2. **Progressive Backoff**: Increase polling interval for longer operations
3. **Status Persistence**: Store progress in database for recovery across server restarts
4. **Real-time Notifications**: Add browser notifications when tab is inactive
5. **Bandwidth Optimization**: Use delta updates in polling responses

