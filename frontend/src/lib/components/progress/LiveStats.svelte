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
  <div class="bg-white/50 backdrop-blur-sm p-4 rounded-2xl border border-gray-100 flex items-center gap-4">
    <div class="p-2 rounded-xl bg-blue-50 text-blue-600">
      <Timer class="w-5 h-5" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">Time Elapsed</p>
      <p class="text-xl font-black text-contrast tabular-nums">{formatTime(stats.elapsedSeconds)}</p>
    </div>
  </div>

  <div class="bg-white/50 backdrop-blur-sm p-4 rounded-2xl border border-gray-100 flex items-center gap-4">
    <div class="p-2 rounded-xl bg-accent/10 text-accent">
      <Zap class="w-5 h-5" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">Tokens Ingested</p>
      <p class="text-xl font-black text-contrast tabular-nums">{formatTokens(stats.tokens_used)}</p>
    </div>
  </div>

  <div class="bg-white/50 backdrop-blur-sm p-4 rounded-2xl border border-gray-100 flex items-center gap-4">
    <div class="p-2 rounded-xl bg-purple-50 text-purple-600">
      <Brain class="w-5 h-5" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">AI Engine</p>
      <p class="text-sm font-black text-contrast">{stats.model.toUpperCase()}</p>
    </div>
  </div>

  <div class="bg-white/50 backdrop-blur-sm p-4 rounded-2xl border border-gray-100 flex items-center gap-4">
    <div class="p-2 rounded-xl bg-amber-50 text-amber-600">
      <Activity class="w-5 h-5 animate-pulse" />
    </div>
    <div>
      <p class="text-[10px] font-black uppercase tracking-wider text-gray-400">System Load</p>
      <p class="text-sm font-black text-contrast">Optimized</p>
    </div>
  </div>
</div>

