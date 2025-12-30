<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Bot, Check, Copy, RefreshCw } from 'lucide-svelte';
  import { toastStore } from '$lib/stores/toastStore';
  import { slide, fade } from 'svelte/transition';

  let { 
    endpoint,
    authToken,
    onComplete,
    title = "AI Generating Response..."
  }: { 
    endpoint: string;
    authToken: string;
    onComplete?: (fullText: string) => void;
    title?: string;
  } = $props();

  let text = $state('');
  let isStreaming = $state(true);
  let eventSource: EventSource | null = null;
  let error = $state<string | null>(null);

  onMount(() => {
    startStreaming();
  });

  onDestroy(() => {
    stopStreaming();
  });

  function startStreaming() {
    text = '';
    isStreaming = true;
    error = null;

    // Use URL with token for auth if needed, or custom header if your backend supports it
    // EventSource doesn't support custom headers easily, so we use query param
    const url = new URL(endpoint);
    url.searchParams.append('token', authToken);

    eventSource = new EventSource(url.toString());

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.token) {
          text += data.token;
        }
        if (data.done) {
          isStreaming = false;
          stopStreaming();
          onComplete?.(text);
        }
      } catch (err) {
        console.error('Failed to parse streaming token:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('Streaming error:', err);
      error = "Connection lost. Reconnecting...";
      // Browser handles reconnection automatically for EventSource
    };
  }

  function stopStreaming() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function copyToClipboard() {
    navigator.clipboard.writeText(text);
    toastStore.success('Copied to clipboard');
  }
</script>

<div class="flex flex-col h-full bg-contrast rounded-2xl border border-white/10 shadow-2xl overflow-hidden shadow-black/40">
  <!-- Header -->
  <div class="px-6 py-4 bg-white/5 border-b border-white/10 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="p-2 rounded-lg bg-accent/20 text-accent">
        {#if isStreaming}
          <RefreshCw class="w-4 h-4 animate-spin" />
        {:else}
          <Bot class="w-4 h-4" />
        {/if}
      </div>
      <h3 class="text-sm font-bold text-white tracking-tight">{title}</h3>
    </div>

    {#if !isStreaming && text}
      <button 
        onclick={copyToClipboard}
        class="p-2 rounded-lg bg-white/5 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
        title="Copy to clipboard"
      >
        <Copy class="w-4 h-4" />
      </button>
    {/if}
  </div>

  <!-- Content -->
  <div class="flex-1 overflow-y-auto p-6 custom-scrollbar bg-black/20">
    {#if error && isStreaming}
      <div class="mb-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-center gap-2" transition:slide>
        <RefreshCw class="w-3 h-3 animate-spin" />
        {error}
      </div>
    {/if}

    <div class="prose prose-invert prose-sm max-w-none">
      <pre class="whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-gray-200 selection:bg-accent selection:text-white">
        {text}<span class={isStreaming ? 'animate-cursor text-accent ml-0.5' : 'hidden'}>▌</span>
      </pre>
    </div>

    {#if !text && isStreaming}
      <div class="flex flex-col items-center justify-center py-20 text-gray-500 italic" in:fade>
        <div class="flex gap-1 mb-2">
          <div class="w-1.5 h-1.5 rounded-full bg-gray-600 animate-bounce" style="animation-delay: 0s"></div>
          <div class="w-1.5 h-1.5 rounded-full bg-gray-600 animate-bounce" style="animation-delay: 0.2s"></div>
          <div class="w-1.5 h-1.5 rounded-full bg-gray-600 animate-bounce" style="animation-delay: 0.4s"></div>
        </div>
        <p class="text-xs">Neural engine is preparing response...</p>
      </div>
    {/if}
  </div>

  <!-- Footer -->
  <div class="px-6 py-3 bg-white/5 border-t border-white/10 flex items-center justify-between text-[10px]">
    <div class="flex items-center gap-2 text-gray-500">
      <span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
      Streaming from GPT-4o
    </div>
    {#if !isStreaming && text}
      <div class="text-accent font-bold uppercase tracking-widest flex items-center gap-1">
        <Check class="w-3 h-3" />
        Generation Complete
      </div>
    {/if}
  </div>
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 10px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.2);
  }
</style>

