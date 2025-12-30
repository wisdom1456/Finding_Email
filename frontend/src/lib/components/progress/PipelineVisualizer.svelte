<script lang="ts">
  import StageCard from './StageCard.svelte';
  import type { StageState } from './StageCard.svelte';
  import { ArrowRight } from 'lucide-svelte';

  let { 
    stages = [] 
  }: { 
    stages: StageState[] 
  } = $props();

  const activeIndex = $derived(stages.findIndex(s => s.status === 'active' || s.status === 'pending'));
</script>

<div class="relative w-full overflow-hidden py-8">
  <div class="grid grid-cols-1 md:grid-cols-5 gap-4 relative">
    {#each stages as stage, i}
      <div class="relative flex flex-col items-center">
        <StageCard 
          {stage} 
          isActive={stage.status === 'active'} 
        />
        
        {#if i < stages.length - 1}
          <div class="hidden md:flex absolute top-1/2 -right-4 -translate-y-1/2 z-0">
            <ArrowRight class={`w-4 h-4 transition-colors duration-500 ${stage.status === 'completed' ? 'text-accent' : 'text-gray-600'}`} />
          </div>
          
          <!-- Particle Flow Effect -->
          {#if stage.status === 'active' || (stage.status === 'completed' && stages[i+1]?.status === 'active')}
            <div class="hidden md:block absolute top-1/2 right-0 w-full h-px z-0 pointer-events-none">
              <div class="animate-particle absolute top-0 left-0 w-2 h-2 bg-accent rounded-full blur-[1px]"></div>
              <div class="animate-particle absolute top-0 left-0 w-2 h-2 bg-accent rounded-full blur-[1px]" style="animation-delay: 1s"></div>
              <div class="animate-particle absolute top-0 left-0 w-2 h-2 bg-accent rounded-full blur-[1px]" style="animation-delay: 2s"></div>
            </div>
          {/if}
        {/if}
      </div>
    {/each}
  </div>
</div>

<style>
  /* Particle flow is mostly handled by global CSS */
</style>

