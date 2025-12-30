<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { fade, scale } from 'svelte/transition';
  import { Bot, Terminal, X, AlertCircle } from 'lucide-svelte';
  import PipelineVisualizer from './PipelineVisualizer.svelte';
  import DocumentFlowVisualizer from './DocumentFlowVisualizer.svelte';
  import LiveStats from './LiveStats.svelte';
  import { progressStore } from '$lib/stores/progressStore';
  import type { EnhancedProgressState } from '$lib/stores/progressStore';

  let { 
    analysisId,
    onComplete,
    onError
  }: { 
    analysisId: string;
    onComplete?: () => void;
    onError?: (error: string) => void;
  } = $props();

  // Use the enhanced progress store
  let state = $derived($progressStore as EnhancedProgressState);
  
  // Track previous status to detect transition to completed/error
  let prevStatus = '';

  $effect(() => {
    if (state.status === 'completed' && prevStatus !== 'completed') {
      setTimeout(() => onComplete?.(), 2000);
    }
    if (state.status === 'error' && prevStatus !== 'error') {
      onError?.(state.message || 'An unknown error occurred during analysis');
    }
    prevStatus = state.status;
  });

  onMount(async () => {
    // Start listening to the analysis stream
    await progressStore.startListening(analysisId);
  });

  onDestroy(() => {
    progressStore.stopListening();
  });
</script>

<div 
  class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-contrast/95 backdrop-blur-md"
  transition:fade={{ duration: 300 }}
>
  <div 
    class="relative w-full max-w-6xl max-h-[95vh] bg-[#181A31] border border-white/10 rounded-[2.5rem] shadow-2xl flex flex-col overflow-hidden"
    transition:scale={{ duration: 400, start: 0.95 }}
  >
    <!-- Header -->
    <div class="px-8 pt-8 pb-4 flex items-center justify-between border-b border-white/5">
      <div class="flex items-center gap-4">
        <div class="p-3 rounded-2xl bg-accent shadow-lg shadow-accent/20">
          <Bot class="w-8 h-8 text-white" />
        </div>
        <div>
          <h2 class="text-2xl font-black text-white tracking-tight">AI Command Center</h2>
          <div class="flex items-center gap-2 mt-1">
            <div class="w-2 h-2 rounded-full bg-accent animate-pulse"></div>
            <p class="text-xs font-bold text-accent uppercase tracking-widest">
              {state.message || 'Initializing Legal Brain...'}
            </p>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-4">
        <div class="px-4 py-2 rounded-xl bg-white/5 border border-white/10 flex items-center gap-3">
          <Terminal class="w-4 h-4 text-gray-400" />
          <span class="text-[10px] font-mono text-gray-400">ID: {analysisId.slice(0, 8)}...</span>
        </div>
      </div>
    </div>

    <!-- Main Viewport -->
    <div class="flex-1 overflow-y-auto p-8 space-y-10 custom-scrollbar">
      
      <!-- Part 1: Strategic Pipeline -->
      <div>
        <div class="flex items-center gap-3 mb-2">
          <div class="w-1.5 h-1.5 rounded-full bg-accent"></div>
          <h3 class="text-sm font-black text-white uppercase tracking-widest opacity-60">Strategic Pipeline</h3>
        </div>
        <PipelineVisualizer stages={state.stages} />
      </div>

      <!-- Part 2: Live Statistics -->
      <LiveStats stats={state.stats} />

      <!-- Part 3: Real-time Extraction Engine -->
      <div>
        <div class="flex items-center gap-3 mb-6">
          <div class="w-1.5 h-1.5 rounded-full bg-accent"></div>
          <h3 class="text-sm font-black text-white uppercase tracking-widest opacity-60">Real-time Extraction Engine</h3>
        </div>
        <DocumentFlowVisualizer documents={state.documents} />
      </div>

      <!-- Part 4: Intelligent Log -->
      <div class="bg-black/40 rounded-2xl p-6 border border-white/5 font-mono">
        <div class="flex items-center gap-2 mb-4">
          <Terminal class="w-4 h-4 text-accent" />
          <span class="text-xs font-bold text-accent uppercase tracking-widest">Intelligent Log</span>
        </div>
        <div class="space-y-2 max-h-40 overflow-y-auto text-[11px]">
          {#if state.status === 'processing' || state.status === 'initialization'}
            <div class="text-gray-400 flex gap-3">
              <span class="text-accent opacity-50">[{new Date().toLocaleTimeString()}]</span>
              <span>Establishing secure connection to neural processing clusters...</span>
            </div>
            <div class="text-gray-400 flex gap-3">
              <span class="text-accent opacity-50">[{new Date().toLocaleTimeString()}]</span>
              <span>Loading legal corpus for {state.stats.model}...</span>
            </div>
          {/if}
          
          {#if state.message}
            <div class="text-white flex gap-3 animate-fade-in-up">
              <span class="text-accent opacity-50">[{new Date().toLocaleTimeString()}]</span>
              <span class="font-bold">{state.message}</span>
            </div>
          {/if}

          {#if state.sub_step}
            <div class="text-accent/80 flex gap-3 animate-fade-in-up">
              <span class="text-accent opacity-30">[{new Date().toLocaleTimeString()}]</span>
              <span class="italic">→ {state.sub_step}</span>
            </div>
          {/if}
        </div>
      </div>
    </div>

    <!-- Footer Overlay for Errors -->
    {#if state.status === 'error'}
      <div class="absolute inset-x-0 bottom-0 p-8 bg-red-500/10 backdrop-blur-xl border-t border-red-500/20 flex items-center justify-between">
        <div class="flex items-center gap-4 text-red-400">
          <AlertCircle class="w-8 h-8" />
          <div>
            <p class="text-lg font-black tracking-tight text-white">Neural Process Failure</p>
            <p class="text-sm font-medium opacity-80">{state.message}</p>
          </div>
        </div>
        <button 
          onclick={() => onError?.(state.message || 'Analysis failed')}
          class="px-6 py-3 rounded-xl bg-white text-red-600 font-black text-sm hover:bg-gray-100 transition-all"
        >
          CLOSE PROTOCOL
        </button>
      </div>
    {/if}

    <!-- Completion Overlay -->
    {#if state.status === 'completed'}
      <div class="absolute inset-0 z-50 bg-accent/90 backdrop-blur-md flex flex-col items-center justify-center text-white" transition:fade>
        <div class="p-6 rounded-full bg-white text-accent mb-6 shadow-2xl animate-bounce">
          <Bot class="w-16 h-12" />
        </div>
        <h2 class="text-4xl font-black tracking-tighter mb-2 text-center">ANALYSIS READY</h2>
        <p class="text-lg font-bold opacity-80 text-center max-w-md">The AI has completed the strategic assessment. Synchronizing results...</p>
      </div>
    {/if}
  </div>
</div>

<style>
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 10px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 10px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.2);
  }
</style>

