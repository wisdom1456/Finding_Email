<script lang="ts">
  import StageCard from './StageCard.svelte';
  import type { StageState } from './StageCard.svelte';
  import { ChevronRight } from 'lucide-svelte';

  let { 
    stages = [] 
  }: { 
    stages: StageState[] 
  } = $props();
</script>

<div class="w-full py-4 overflow-x-auto custom-scrollbar">
  <div class="flex flex-nowrap items-center justify-between gap-2 min-w-[900px] md:min-w-0">
    {#each stages as stage, i}
      <div class="flex-1 min-w-[160px] relative">
        <StageCard 
          {stage} 
          isActive={stage.status === 'active'} 
        />
      </div>
      
      {#if i < stages.length - 1}
        <div class="hidden md:flex items-center justify-center px-1">
          <ChevronRight class={`w-5 h-5 ${stage.status === 'completed' ? 'text-accent' : 'text-white/20'}`} />
        </div>
      {/if}
    {/each}
  </div>
</div>

<style>
  /* Simplified layout to prevent overlap */
</style>
