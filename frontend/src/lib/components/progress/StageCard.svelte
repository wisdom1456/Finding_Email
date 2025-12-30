<script lang="ts">
  import { CheckCircle, Loader2, Circle, AlertCircle } from 'lucide-svelte';
  import { slide } from 'svelte/transition';
  
  export interface StageState {
    id: string;
    name: string;
    status: 'pending' | 'active' | 'completed' | 'error';
    progress: number;
    startedAt?: string;
    completedAt?: string;
    extracted?: { type: string; count: number; preview?: string[] };
  }

  let { 
    stage,
    isActive = false 
  }: { 
    stage: StageState;
    isActive?: boolean;
  } = $props();
  
  const statusConfig = {
    pending: { icon: Circle, color: 'text-gray-400', bg: 'bg-gray-100', borderColor: 'border-transparent' },
    active: { icon: Loader2, color: 'text-accent', bg: 'bg-accent/10', borderColor: 'border-accent' },
    completed: { icon: CheckCircle, color: 'text-accent', bg: 'bg-accent/5', borderColor: 'border-accent/30' },
    error: { icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-50', borderColor: 'border-red-200' },
  };
  
  const config = $derived(statusConfig[stage.status]);
</script>

<div class={`
  relative p-4 rounded-xl border-2 transition-all duration-500
  ${config.bg} 
  ${config.borderColor}
  ${isActive ? 'animate-stage-pulse shadow-lg z-10' : 'shadow-sm'}
`}>
  <div class="flex items-center gap-3">
    <div class={`p-2 rounded-lg bg-white shadow-sm ${config.color}`}>
      <svelte:component 
        this={config.icon} 
        class={`w-6 h-6 ${stage.status === 'active' ? 'animate-spin' : ''}`}
      />
    </div>
    <div class="flex-1 min-w-0">
      <h4 class="font-bold text-sm text-contrast truncate">{stage.name}</h4>
      {#if stage.extracted}
        <p class="text-[10px] font-bold uppercase tracking-wider text-accent mt-0.5" in:slide>
          {stage.extracted.count} {stage.extracted.type} found
        </p>
      {:else if stage.status === 'active'}
        <p class="text-[10px] font-medium text-gray-500 mt-0.5 animate-pulse">
          Processing...
        </p>
      {:else if stage.status === 'completed'}
        <p class="text-[10px] font-medium text-green-600 mt-0.5">
          Completed
        </p>
      {/if}
    </div>
  </div>
  
  {#if stage.status === 'active'}
    <div class="mt-3 h-1.5 bg-gray-200/50 rounded-full overflow-hidden">
      <div 
        class="h-full bg-accent transition-all duration-1000 ease-out"
        style="width: {Math.max(5, stage.progress)}%"
      />
    </div>
  {/if}

  {#if stage.status === 'completed'}
    <div class="absolute -top-2 -right-2 bg-accent text-white p-1 rounded-full shadow-lg">
      <CheckCircle class="w-3 h-3" />
    </div>
  {/if}
</div>

<style>
  /* Local styles if needed */
</style>

