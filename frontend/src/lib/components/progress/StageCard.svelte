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
  
  // High contrast dark theme status config
  const statusConfig = {
    pending: { 
      icon: Circle, 
      color: 'text-white/30', 
      bg: 'bg-white/5', 
      borderColor: 'border-white/10',
      titleColor: 'text-white/40'
    },
    active: { 
      icon: Loader2, 
      color: 'text-accent', 
      bg: 'bg-accent/15', 
      borderColor: 'border-accent',
      titleColor: 'text-white font-black'
    },
    completed: { 
      icon: CheckCircle, 
      color: 'text-accent', 
      bg: 'bg-accent/10', 
      borderColor: 'border-accent/40',
      titleColor: 'text-white font-bold'
    },
    error: { 
      icon: AlertCircle, 
      color: 'text-red-400', 
      bg: 'bg-red-500/20', 
      borderColor: 'border-red-400',
      titleColor: 'text-white font-bold'
    },
  };
  
  const config = $derived(statusConfig[stage.status]);
</script>

<div class={`
  relative p-3 rounded-xl border-2 transition-all duration-500
  ${config.bg} 
  ${config.borderColor}
  ${isActive ? 'ring-4 ring-accent/20 scale-[1.02] z-10 shadow-2xl shadow-accent/20' : 'opacity-80'}
`}>
  <div class="flex items-center gap-3">
    <div class={`p-2 rounded-lg bg-black/40 backdrop-blur-md border border-white/5 ${config.color}`}>
      <svelte:component 
        this={config.icon} 
        class={`w-5 h-5 ${stage.status === 'active' ? 'animate-spin' : ''}`}
      />
    </div>
    <div class="flex-1 min-w-0">
      <h4 class={`text-xs uppercase tracking-tight truncate ${config.titleColor}`}>{stage.name}</h4>
      
      {#if stage.extracted}
        <p class="text-[10px] font-black uppercase tracking-widest text-accent mt-0.5" in:slide>
          {stage.extracted.count} {stage.extracted.type}
        </p>
      {:else if stage.status === 'active'}
        <div class="flex items-center gap-1.5 mt-0.5">
          <span class="w-1 h-1 rounded-full bg-accent animate-ping"></span>
          <p class="text-[9px] font-bold text-accent uppercase tracking-widest">Processing</p>
        </div>
      {:else if stage.status === 'completed'}
        <p class="text-[9px] font-bold text-accent/60 uppercase tracking-widest mt-0.5">Ready</p>
      {:else}
        <p class="text-[9px] font-bold text-white/20 uppercase tracking-widest mt-0.5">Queue</p>
      {/if}
    </div>
  </div>
  
  {#if stage.status === 'active'}
    <div class="mt-2 h-1 bg-black/40 rounded-full overflow-hidden border border-white/5">
      <div 
        class="h-full bg-accent shadow-[0_0_8px_rgba(var(--color-accent-rgb),0.5)] transition-all duration-1000 ease-out"
        style="width: {Math.max(5, stage.progress)}%"
      />
    </div>
  {/if}
</div>
