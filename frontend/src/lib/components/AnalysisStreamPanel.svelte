<!--
  AnalysisStreamPanel - Live streaming case analysis display
  
  Features:
  - Streams markdown content from GPT-5.2 medium in real-time
  - Two-phase UX: "thinking" (AI reasoning) then "streaming" (tokens flowing)
  - Renders markdown as it arrives (like ChatGPT)
  - Auto-scrolls to show new content
  - Copy to clipboard functionality
  - Expandable panel design (not modal - doesn't block page)
  - Abort streaming capability
-->
<script lang="ts">
  import { marked } from 'marked';
  import { Copy, X, RotateCcw, Loader2, CheckCircle2, AlertCircle, Brain } from 'lucide-svelte';
  import { slide } from 'svelte/transition';
  import { getApiUrl } from '$lib/config';
  import { getSecureSession } from '$lib/supabase';

  type StreamStatus = 'idle' | 'thinking' | 'streaming' | 'complete' | 'error';

  let {
    caseId,
    onComplete,
    onError,
  }: {
    caseId: string;
    onComplete?: (content: string) => void;
    onError?: (error: string) => void;
  } = $props();

  let content = $state('');
  let status: StreamStatus = $state('idle');
  let errorMessage = $state('');
  let panelElement: HTMLDivElement;
  let abortController: AbortController | null = null;
  let copySuccess = $state(false);
  let startTime = $state(0);
  let elapsedTime = $state(0);
  let thinkingTime = $state(0);  // Time spent in thinking phase
  let timerInterval: ReturnType<typeof setInterval> | null = null;
  let copyResetTimer: ReturnType<typeof setTimeout> | null = null;
  let hasEmittedComplete = $state(false);
  // Scope counts surfaced from the done event — non-zero docs_omitted triggers a warning banner
  let docsInScope = $state(0);
  let docsOmitted = $state(0);
  // Track save failures so the user can retry
  let saveError = $state(false);
  let savePendingContent = $state('');

  // Rendered HTML from markdown
  let renderedHtml = $derived.by(() => {
    if (!content) return '';
    try {
      return marked(content, { breaks: true, gfm: true });
    } catch {
      return content;
    }
  });

  // Start streaming analysis using fetch (supports Authorization header)
  export async function startStreaming() {
    if (status === 'streaming' || status === 'thinking') return;
    
    content = '';
    status = 'thinking';  // Start in thinking phase
    hasEmittedComplete = false;
    errorMessage = '';
    startTime = Date.now();
    elapsedTime = 0;
    thinkingTime = 0;
    docsInScope = 0;
    docsOmitted = 0;
    
    // Start elapsed time counter
    timerInterval = setInterval(() => {
      elapsedTime = Math.floor((Date.now() - startTime) / 1000);
    }, 1000);

    // Create abort controller for cancellation
    abortController = new AbortController();

    try {
      // Get auth token (securely validated)
      const { session, user } = await getSecureSession();
      if (!session || !user) {
        throw new Error('Not authenticated. Please log in again.');
      }

      const apiUrl = getApiUrl();
      const url = `${apiUrl}/api/analysis/stream/${caseId}`;
      
      // Use fetch with Authorization header (EventSource doesn't support custom headers)
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Accept': 'text/event-stream',
        },
        signal: abortController.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `HTTP ${response.status}: Failed to start analysis`);
      }

      if (!response.body) {
        throw new Error('No response body received');
      }

      // Read the stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          // Stream ended - check if we got completion signal
          if (status === 'streaming') {
            emitComplete(content);
          }
          break;
        }

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });
        
        // Process complete SSE lines from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              // Handle phase transitions
              if (data.phase === 'thinking') {
                status = 'thinking';
                // Update thinking elapsed time from server
                if (data.elapsed !== undefined) {
                  // Server sends elapsed time during thinking
                }
              }
              
              if (data.phase === 'streaming') {
                // Transition from thinking to streaming
                status = 'streaming';
                thinkingTime = data.thinking_time || elapsedTime;
                console.log(`AI thinking completed in ${thinkingTime}s, now streaming...`);
              }
              
              if (data.token) {
                // Ensure we're in streaming status when tokens arrive
                if (status === 'thinking') {
                  status = 'streaming';
                  thinkingTime = elapsedTime;
                }
                content += data.token;
                // Auto-scroll to bottom
                if (panelElement) {
                  requestAnimationFrame(() => {
                    panelElement.scrollTop = panelElement.scrollHeight;
                  });
                }
              }
              
              // Heartbeat - just keep connection alive, no action needed
              if (data.heartbeat !== undefined) {
                // Connection is alive
              }
              
              if (data.done) {
                // Capture scope counts before emitting complete
                if (data.docs_in_scope !== undefined) docsInScope = data.docs_in_scope;
                if (data.docs_omitted !== undefined) docsOmitted = data.docs_omitted;
                emitComplete(content);
              }
              
              if (data.error) {
                status = 'error';
                errorMessage = data.error;
                stopTimer();
                onError?.(data.error);
              }
            } catch (e) {
              // Skip lines that aren't valid JSON (like empty lines)
              if (line.slice(6).trim()) {
                console.warn('Error parsing SSE data:', e, line);
              }
            }
          }
        }
      }
      
    } catch (e) {
      // Don't report error if aborted by user
      if (e instanceof Error && e.name === 'AbortError') {
        status = 'idle';
        stopTimer();
        return;
      }
      
      console.error('Streaming error:', e);
      status = 'error';
      errorMessage = e instanceof Error ? e.message : 'Failed to start streaming';
      stopTimer();
      onError?.(errorMessage);
    }
  }

  function emitComplete(analysisContent: string) {
    if (hasEmittedComplete) return;
    hasEmittedComplete = true;
    status = 'complete';
    stopTimer();
    void saveAnalysis(analysisContent);
    onComplete?.(analysisContent);
  }

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  // Abort streaming
  function abortStreaming() {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    status = 'idle';
    stopTimer();
  }

  // Copy content to clipboard
  async function copyToClipboard() {
    try {
      await navigator.clipboard.writeText(content);
      copySuccess = true;
      if (copyResetTimer) clearTimeout(copyResetTimer);
      copyResetTimer = setTimeout(() => {
        copySuccess = false;
      }, 2000);
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  }

  // Save the analysis result to the database
  async function saveAnalysis(analysisContent: string) {
    saveError = false;
    savePendingContent = analysisContent;
    try {
      const { session, user } = await getSecureSession();
      if (!session || !user) {
        console.error('No session for saving analysis');
        saveError = true;
        return;
      }

      const apiUrl = getApiUrl();
      const response = await fetch(`${apiUrl}/api/analysis/stream/${caseId}/save`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ content: analysisContent }),
      });

      if (!response.ok) {
        console.error('Failed to save analysis:', await response.text());
        saveError = true;
      } else {
        console.log('Streaming analysis saved successfully');
        savePendingContent = '';
      }
    } catch (e) {
      console.error('Error saving analysis:', e);
      saveError = true;
    }
  }

  // Retry saving analysis after a failure
  function retrySave() {
    if (savePendingContent) {
      void saveAnalysis(savePendingContent);
    }
  }

  // Retry after error
  function retry() {
    startStreaming();
  }

  // Format elapsed time
  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  }

  // Cleanup on destroy
  $effect(() => {
    return () => {
      if (abortController) {
        abortController.abort();
      }
      stopTimer();
      if (copyResetTimer) {
        clearTimeout(copyResetTimer);
        copyResetTimer = null;
      }
    };
  });
</script>

<div class="analysis-stream-panel" transition:slide={{ duration: 200 }}>
  <!-- Header -->
  <div class="panel-header">
    <div class="header-left">
      <h3 class="panel-title">
        {#if status === 'thinking'}
          <Brain class="h-5 w-5 text-purple-500 animate-pulse" />
        {:else if status === 'streaming'}
          <Loader2 class="h-5 w-5 animate-spin text-blue-500" />
        {:else if status === 'complete'}
          <CheckCircle2 class="h-5 w-5 text-green-500" />
        {:else if status === 'error'}
          <AlertCircle class="h-5 w-5 text-red-500" />
        {/if}
        <span>Case Analysis</span>
      </h3>
      
      {#if status === 'thinking' || status === 'streaming' || status === 'complete'}
        <span class="elapsed-time">
          {formatTime(elapsedTime)}
        </span>
      {/if}
    </div>
    
    <div class="header-actions">
      {#if status === 'complete' && content}
        <button
          class="action-btn"
          onclick={copyToClipboard}
          title="Copy to clipboard"
        >
          {#if copySuccess}
            <CheckCircle2 class="h-4 w-4 text-green-500" />
          {:else}
            <Copy class="h-4 w-4" />
          {/if}
        </button>
      {/if}
      
      {#if status === 'error'}
        <button
          class="action-btn"
          onclick={retry}
          title="Retry analysis"
        >
          <RotateCcw class="h-4 w-4" />
        </button>
      {/if}
      
      {#if status === 'thinking' || status === 'streaming'}
        <button
          class="action-btn text-red-500 hover:text-red-700"
          onclick={abortStreaming}
          title="Cancel analysis"
        >
          <X class="h-4 w-4" />
        </button>
      {/if}
    </div>
  </div>

  <!-- Content -->
  <div 
    class="panel-content" 
    bind:this={panelElement}
  >
    {#if status === 'idle'}
      <div class="empty-state">
        <p>Click "Start Analysis" to begin streaming case analysis.</p>
      </div>
    {:else if status === 'error'}
      <div class="error-state">
        <AlertCircle class="h-8 w-8 text-red-400" />
        <p>{errorMessage}</p>
        <button class="retry-btn" onclick={retry}>
          <RotateCcw class="h-4 w-4" />
          Retry Analysis
        </button>
      </div>
    {:else if status === 'thinking'}
      <div class="thinking-state">
        <div class="thinking-icon-container">
          <Brain class="h-12 w-12 text-purple-500" />
          <div class="thinking-pulse"></div>
        </div>
        <h4 class="thinking-title">AI is reasoning...</h4>
        <p class="thinking-description">
          GPT-5.2 is analyzing your documents and building a comprehensive legal analysis.
        </p>
        <p class="thinking-time">Usually takes 30-60 seconds</p>
        <div class="thinking-elapsed">{formatTime(elapsedTime)}</div>
      </div>
    {:else if content}
      <article class="prose prose-slate max-w-none">
        {@html renderedHtml}
      </article>
      {#if status === 'streaming'}
        <span class="cursor-blink">▌</span>
      {/if}
    {:else if status === 'streaming'}
      <div class="loading-state">
        <Loader2 class="h-6 w-6 animate-spin text-blue-500" />
        <p>Starting analysis stream...</p>
      </div>
    {/if}
  </div>

  <!-- Scope warning — shown when the AI analyzed fewer docs than the case contains -->
  {#if status === 'complete' && docsOmitted > 0}
    <div class="scope-warning">
      <span class="scope-warning-icon">⚠</span>
      <span>
        {docsInScope} of {docsInScope + docsOmitted} documents were included in this analysis.
        Large cases may not include all documents in the AI summary.
      </span>
    </div>
  {/if}

  <!-- Save error banner -->
  {#if saveError && status === 'complete'}
    <div class="save-error-banner">
      <AlertCircle class="h-4 w-4" />
      <span>Analysis completed but couldn't be saved.</span>
      <button class="save-retry-btn" onclick={retrySave}>Retry Save</button>
    </div>
  {/if}

  <!-- Status bar -->
  {#if status === 'thinking'}
    <div class="status-bar thinking">
      <div class="status-indicator thinking"></div>
      <span>GPT-5.2 is reasoning about your case...</span>
    </div>
  {:else if status === 'streaming'}
    <div class="status-bar">
      <div class="status-indicator streaming"></div>
      <span>Streaming analysis{thinkingTime > 0 ? ` (thought for ${formatTime(thinkingTime)})` : ''}...</span>
    </div>
  {:else if status === 'complete'}
    <div class="status-bar complete">
      <div class="status-indicator complete"></div>
      <span>Analysis complete in {formatTime(elapsedTime)}{thinkingTime > 0 ? ` (${formatTime(thinkingTime)} thinking)` : ''}</span>
    </div>
  {/if}
</div>

<style>
  .analysis-stream-panel {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
    height: 100%;
    max-height: 80vh;
    overflow: hidden;
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid #e5e7eb;
    background: #f9fafb;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .panel-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 600;
    color: #111827;
    margin: 0;
  }

  .elapsed-time {
    font-size: 13px;
    color: #6b7280;
    font-variant-numeric: tabular-nums;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .action-btn {
    padding: 6px;
    border-radius: 6px;
    color: #6b7280;
    transition: all 0.15s;
    background: transparent;
    border: none;
    cursor: pointer;
  }

  .action-btn:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .panel-content {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    scroll-behavior: smooth;
  }

  .empty-state,
  .loading-state,
  .error-state,
  .thinking-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    text-align: center;
    color: #6b7280;
    gap: 12px;
  }

  .error-state {
    color: #dc2626;
  }

  /* Thinking phase styles */
  .thinking-state {
    gap: 16px;
    padding: 60px 40px;
  }

  .thinking-icon-container {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .thinking-pulse {
    position: absolute;
    width: 80px;
    height: 80px;
    border-radius: 50%;
    background: rgba(168, 85, 247, 0.15);
    animation: thinking-pulse-anim 2s ease-in-out infinite;
  }

  @keyframes thinking-pulse-anim {
    0%, 100% {
      transform: scale(0.9);
      opacity: 0.5;
    }
    50% {
      transform: scale(1.2);
      opacity: 0.2;
    }
  }

  .thinking-title {
    font-size: 18px;
    font-weight: 600;
    color: #7c3aed;
    margin: 8px 0 0 0;
  }

  .thinking-description {
    font-size: 14px;
    color: #6b7280;
    max-width: 300px;
    line-height: 1.5;
  }

  .thinking-time {
    font-size: 13px;
    color: #9ca3af;
    font-style: italic;
  }

  .thinking-elapsed {
    font-size: 32px;
    font-weight: 700;
    color: #7c3aed;
    font-variant-numeric: tabular-nums;
    margin-top: 8px;
  }

  .retry-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    background: #fee2e2;
    color: #dc2626;
    border: none;
    border-radius: 6px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
  }

  .retry-btn:hover {
    background: #fecaca;
  }

  /* Prose styling for markdown */
  .prose {
    font-size: 15px;
    line-height: 1.7;
    color: #374151;
  }

  .prose :global(h2) {
    font-size: 20px;
    font-weight: 700;
    color: #111827;
    margin-top: 24px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 2px solid #e5e7eb;
  }

  .prose :global(h3) {
    font-size: 17px;
    font-weight: 600;
    color: #1f2937;
    margin-top: 20px;
    margin-bottom: 8px;
  }

  .prose :global(p) {
    margin-bottom: 12px;
  }

  .prose :global(ul),
  .prose :global(ol) {
    margin-bottom: 12px;
    padding-left: 24px;
  }

  .prose :global(li) {
    margin-bottom: 6px;
  }

  .prose :global(strong) {
    font-weight: 600;
    color: #111827;
  }

  .prose :global(code) {
    background: #f3f4f6;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 14px;
  }

  /* Blinking cursor effect */
  .cursor-blink {
    display: inline-block;
    color: #3b82f6;
    animation: blink 1s step-end infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  .status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: #f0f9ff;
    border-top: 1px solid #e0f2fe;
    font-size: 13px;
    color: #0369a1;
  }

  .status-bar.complete {
    background: #f0fdf4;
    border-top-color: #dcfce7;
    color: #15803d;
  }

  .status-bar.thinking {
    background: #faf5ff;
    border-top-color: #f3e8ff;
    color: #7c3aed;
  }

  .status-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .status-indicator.thinking {
    background: #a855f7;
    animation: thinking-indicator 1s ease-in-out infinite;
  }

  @keyframes thinking-indicator {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.3); opacity: 0.6; }
  }

  .status-indicator.streaming {
    background: #3b82f6;
    animation: pulse 1.5s ease-in-out infinite;
  }

  .status-indicator.complete {
    background: #22c55e;
  }

  .scope-warning {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 16px;
    background: #fffbeb;
    border-top: 1px solid #fde68a;
    font-size: 13px;
    color: #92400e;
    line-height: 1.4;
  }

  .scope-warning-icon {
    flex-shrink: 0;
    font-size: 14px;
  }

  .save-error-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: #fef2f2;
    border-top: 1px solid #fecaca;
    font-size: 13px;
    color: #991b1b;
  }

  .save-retry-btn {
    margin-left: auto;
    padding: 4px 12px;
    background: #991b1b;
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    white-space: nowrap;
  }

  .save-retry-btn:hover {
    background: #7f1d1d;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
</style>
