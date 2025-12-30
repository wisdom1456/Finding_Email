<script lang="ts">
  import { FileText, FileCheck, FileX, Loader2 } from 'lucide-svelte';
  import { fade, slide } from 'svelte/transition';

  export interface DocumentState {
    id: string;
    name: string;
    status: 'pending' | 'processing' | 'completed' | 'error';
  }

  let { 
    documents = [] 
  }: { 
    documents: DocumentState[] 
  } = $props();

  const processingCount = $derived(documents.filter(d => d.status === 'processing').length);
  const completedCount = $derived(documents.filter(d => d.status === 'completed').length);
  const errorCount = $derived(documents.filter(d => d.status === 'error').length);
</script>

<div class="bg-contrast/5 rounded-2xl p-6 border border-contrast/10">
  <div class="flex items-center justify-between mb-6">
    <h3 class="text-sm font-black uppercase tracking-widest text-contrast/60">
      Document Flow
    </h3>
    <div class="flex gap-4">
      <div class="flex items-center gap-1.5 text-[10px] font-bold text-accent">
        <div class="w-2 h-2 rounded-full bg-accent animate-pulse"></div>
        {processingCount} Processing
      </div>
      <div class="flex items-center gap-1.5 text-[10px] font-bold text-gray-500">
        <div class="w-2 h-2 rounded-full bg-gray-300"></div>
        {completedCount} Ready
      </div>
    </div>
  </div>

  <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
    {#each documents as doc (doc.id)}
      <div 
        class={`
          relative group p-3 rounded-xl border transition-all duration-300
          ${doc.status === 'processing' ? 'bg-accent/5 border-accent animate-pulse' : 'bg-white border-gray-100'}
          ${doc.status === 'completed' ? 'border-accent/30' : ''}
          ${doc.status === 'error' ? 'bg-red-50 border-red-200' : ''}
        `}
        in:fade
      >
        <!-- Scanning Line -->
        {#if doc.status === 'processing'}
          <div class="animate-scan-sweep"></div>
        {/if}

        <div class="flex flex-col items-center text-center gap-2">
          <div class={`
            p-2 rounded-lg 
            ${doc.status === 'processing' ? 'text-accent' : 'text-gray-400'}
            ${doc.status === 'completed' ? 'text-accent' : ''}
            ${doc.status === 'error' ? 'text-red-500' : ''}
          `}>
            {#if doc.status === 'processing'}
              <Loader2 class="w-6 h-6 animate-spin" />
            {:else if doc.status === 'completed'}
              <FileCheck class="w-6 h-6" />
            {:else if doc.status === 'error'}
              <FileX class="w-6 h-6" />
            {:else}
              <FileText class="w-6 h-6" />
            {/if}
          </div>
          <span class="text-[10px] font-bold text-contrast truncate w-full px-1">
            {doc.name}
          </span>
        </div>

        {#if doc.status === 'completed'}
          <div class="absolute -top-1 -right-1 bg-accent text-white p-0.5 rounded-full shadow-sm">
            <FileCheck class="w-2.5 h-2.5" />
          </div>
        {/if}
      </div>
    {/each}
  </div>

  {#if documents.length === 0}
    <div class="py-12 flex flex-col items-center justify-center text-gray-400">
      <FileText class="w-12 h-12 mb-2 opacity-20" />
      <p class="text-xs font-medium">No documents detected in stream yet</p>
    </div>
  {/if}
</div>

