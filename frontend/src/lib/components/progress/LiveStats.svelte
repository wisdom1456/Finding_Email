<script lang="ts">
  import { Timer, Zap, Brain, Activity } from 'lucide-svelte';

  export interface StatsState {
    elapsedSeconds: number;
    estimatedRemaining?: number;
    tokens_used: number;
    model: string;
  }

  let { 
    stats 
  }: { 
    stats: StatsState 
  } = $props();

  function formatTime(seconds: number) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  function formatTokens(tokens: number) {
    if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`;
    if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`;
    return tokens.toString();
  }
</script>

<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
  <!-- Time Elapsed -->
  <div class="bg-white/5 backdrop-blur-sm p-4 rounded-2xl border border-white/10 flex items-center gap-4 hover:bg-white/10 transition-colors">
    <div class="p-2.5 rounded-xl bg-blue-500/20 text-blue-400">
      <Timer class="w-5 h-5" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">Time Elapsed</p>
      <p class="text-xl font-black text-white tabular-nums">{formatTime(stats.elapsedSeconds)}</p>
    </div>
  </div>

  <!-- Tokens Ingested -->
  <div class="bg-white/5 backdrop-blur-sm p-4 rounded-2xl border border-white/10 flex items-center gap-4 hover:bg-white/10 transition-colors">
    <div class="p-2.5 rounded-xl bg-accent/20 text-accent">
      <Zap class="w-5 h-5" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">Tokens Ingested</p>
      <p class="text-xl font-black text-white tabular-nums">{formatTokens(stats.tokens_used)}</p>
    </div>
  </div>

  <!-- AI Engine -->
  <div class="bg-white/5 backdrop-blur-sm p-4 rounded-2xl border border-white/10 flex items-center gap-4 hover:bg-white/10 transition-colors">
    <div class="p-2.5 rounded-xl bg-purple-500/20 text-purple-400">
      <Brain class="w-5 h-5" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">AI Engine</p>
      <p class="text-sm font-black text-white">{stats.model.toUpperCase()}</p>
    </div>
  </div>

  <!-- System Load -->
  <div class="bg-white/5 backdrop-blur-sm p-4 rounded-2xl border border-white/10 flex items-center gap-4 hover:bg-white/10 transition-colors">
    <div class="p-2.5 rounded-xl bg-amber-500/20 text-amber-400">
      <Activity class="w-5 h-5 animate-pulse" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">System Load</p>
      <p class="text-sm font-black text-accent">Optimized</p>
    </div>
  </div>
</div>
