<!--
  SlideOutPanel - Reusable slide-out panel component

  Features:
  - Slides in from the right side of the screen
  - Semi-transparent overlay with backdrop blur
  - Configurable width
  - Keyboard (Escape) and click-outside to close
  - Optional footer slot
  - Accessible with ARIA attributes
-->
<script lang="ts">
  import { fade, fly } from 'svelte/transition';
  import { X } from 'lucide-svelte';

  let {
    open = false,
    title = '',
    width = '65%',
    onClose,
    children,
    footer
  }: {
    open?: boolean;
    title?: string;
    width?: string;
    onClose: () => void;
    children?: any;
    footer?: any;
  } = $props();

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      onClose();
    }
  }

  function handleOverlayClick() {
    onClose();
  }

  function handlePanelClick(event: MouseEvent) {
    event.stopPropagation();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
  <!-- Overlay -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 bg-[rgba(24,26,49,0.6)] backdrop-blur-sm z-40"
    onclick={handleOverlayClick}
    transition:fade={{ duration: 200 }}
  ></div>

  <!-- Panel -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed right-0 top-0 h-full z-50 bg-white border-l border-gray-200 shadow-2xl flex flex-col"
    style="width: {width}"
    role="dialog"
    aria-modal="true"
    aria-labelledby={title ? 'slide-out-panel-title' : undefined}
    tabindex="-1"
    onclick={handlePanelClick}
    transition:fly={{ x: 400, duration: 300 }}
  >
    <!-- Header -->
    <div class="p-4 border-b border-gray-100 flex items-center justify-between flex-shrink-0">
      {#if title}
        <h2
          id="slide-out-panel-title"
          class="font-heading font-semibold text-gray-900 text-lg"
        >
          {title}
        </h2>
      {:else}
        <div></div>
      {/if}

      <button
        onclick={onClose}
        class="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
        aria-label="Close panel"
      >
        <X class="h-5 w-5" />
      </button>
    </div>

    <!-- Body -->
    <div class="flex-1 overflow-y-auto">
      {@render children?.()}
    </div>

    <!-- Footer (optional) -->
    {#if footer}
      <div class="border-t border-gray-100 p-4 flex-shrink-0">
        {@render footer?.()}
      </div>
    {/if}
  </div>
{/if}
