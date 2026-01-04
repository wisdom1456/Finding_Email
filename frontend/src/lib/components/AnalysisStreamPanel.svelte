<!--
  AnalysisStreamPanel - Live streaming case analysis display
  
  Features:
  - Streams markdown content from GPT-4.1 in real-time
  - Renders markdown as it arrives (like ChatGPT)
  - Auto-scrolls to show new content
  - Copy to clipboard functionality
  - Expandable panel design (not modal - doesn't block page)
  - Abort streaming capability
-->
<script lang="ts">
  import { marked } from 'marked';
  import { Copy, X, RotateCcw, Loader2, CheckCircle2, AlertCircle } from 'lucide-svelte';
  import { slide } from 'svelte/transition';
  import { getApiUrl } from '$lib/config';
  import { supabase } from '$lib/supabase';

  type StreamStatus = 'idle' | 'streaming' | 'complete' | 'error';

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
  let eventSource: EventSource | null = null;
  let copySuccess = $state(false);
  let startTime = $state(0);
  let elapsedTime = $state(0);
  let timerInterval: ReturnType<typeof setInterval> | null = null;

  // Rendered HTML from markdown
  let renderedHtml = $derived.by(() => {
    if (!content) return '';
    try {
      return marked(content, { breaks: true, gfm: true });
    } catch {
      return content;
    }
  });

  // Start streaming analysis
  export async function startStreaming() {
    if (status === 'streaming') return;
    
    content = '';
    status = 'streaming';
    errorMessage = '';
    startTime = Date.now();
    elapsedTime = 0;
    
    // Start elapsed time counter
    timerInterval = setInterval(() => {
      elapsedTime = Math.floor((Date.now() - startTime) / 1000);
    }, 1000);

    try {
      const apiUrl = getApiUrl();
      const url = `${apiUrl}/api/analysis/stream/${caseId}`;
      
      eventSource = new EventSource(url, { withCredentials: true });
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.token) {
            content += data.token;
            // Auto-scroll to bottom
            if (panelElement) {
              requestAnimationFrame(() => {
                panelElement.scrollTop = panelElement.scrollHeight;
              });
            }
          }
          
          if (data.done) {
            status = 'complete';
            stopTimer();
            eventSource?.close();
            // Save the streaming analysis to the database
            saveAnalysis(content);
            onComplete?.(content);
          }
          
          if (data.error) {
            status = 'error';
            errorMessage = data.error;
            stopTimer();
            eventSource?.close();
            onError?.(data.error);
          }
        } catch (e) {
          console.error('Error parsing SSE data:', e);
        }
      };
      
      eventSource.onerror = (e) => {
        console.error('SSE error:', e);
        if (status === 'streaming') {
          status = 'error';
          errorMessage = 'Connection lost. Please try again.';
          stopTimer();
          onError?.(errorMessage);
        }
        eventSource?.close();
      };
      
    } catch (e) {
      status = 'error';
      errorMessage = e instanceof Error ? e.message : 'Failed to start streaming';
      stopTimer();
      onError?.(errorMessage);
    }
  }

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  // Abort streaming
  function abortStreaming() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    status = 'idle';
    stopTimer();
  }

  // Copy content to clipboard
  async function copyToClipboard() {
    try {
      await navigator.clipboard.writeText(content);
      copySuccess = true;
      setTimeout(() => copySuccess = false, 2000);
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  }

  // Save the analysis result to the database
  async function saveAnalysis(analysisContent: string) {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        console.error('No session for saving analysis');
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
      } else {
        console.log('Streaming analysis saved successfully');
      }
    } catch (e) {
      console.error('Error saving analysis:', e);
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
      if (eventSource) {
        eventSource.close();
      }
      stopTimer();
    };
  });
</script>

<div class="analysis-stream-panel" transition:slide={{ duration: 200 }}>
  <!-- Header -->
  <div class="panel-header">
    <div class="header-left">
      <h3 class="panel-title">
        {#if status === 'streaming'}
          <Loader2 class="h-5 w-5 animate-spin text-blue-500" />
        {:else if status === 'complete'}
          <CheckCircle2 class="h-5 w-5 text-green-500" />
        {:else if status === 'error'}
          <AlertCircle class="h-5 w-5 text-red-500" />
        {/if}
        <span>Case Analysis</span>
      </h3>
      
      {#if status === 'streaming' || status === 'complete'}
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
      
      {#if status === 'streaming'}
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
        <p>Starting analysis...</p>
      </div>
    {/if}
  </div>

  <!-- Status bar -->
  {#if status === 'streaming'}
    <div class="status-bar">
      <div class="status-indicator streaming"></div>
      <span>Analyzing case with GPT-4.1...</span>
    </div>
  {:else if status === 'complete'}
    <div class="status-bar complete">
      <div class="status-indicator complete"></div>
      <span>Analysis complete in {formatTime(elapsedTime)}</span>
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
  .error-state {
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

  .status-indicator {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .status-indicator.streaming {
    background: #3b82f6;
    animation: pulse 1.5s ease-in-out infinite;
  }

  .status-indicator.complete {
    background: #22c55e;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
</style>

