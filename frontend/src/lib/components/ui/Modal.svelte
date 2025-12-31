<!--
  Modal - Reusable modal/dialog component
  
  Features:
  - Consistent overlay and backdrop blur
  - Keyboard (Escape) and click-outside to close
  - Size variants: sm, md, lg, xl, full
  - Optional close button
  - Accessible with ARIA attributes
-->
<script lang="ts">
  import { fade, scale } from 'svelte/transition';
  import { X } from 'lucide-svelte';

  type Size = 'sm' | 'md' | 'lg' | 'xl' | 'full';

  let {
    open = $bindable(false),
    title = '',
    size = 'md',
    showCloseButton = true,
    closeOnClickOutside = true,
    closeOnEscape = true,
    children,
    footer
  }: {
    open?: boolean;
    title?: string;
    size?: Size;
    showCloseButton?: boolean;
    closeOnClickOutside?: boolean;
    closeOnEscape?: boolean;
    children?: any;
    footer?: any;
  } = $props();

  const sizeClasses: Record<Size, string> = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    full: 'max-w-4xl',
  };

  function handleKeydown(event: KeyboardEvent) {
    if (closeOnEscape && event.key === 'Escape') {
      open = false;
    }
  }

  function handleBackdropClick() {
    if (closeOnClickOutside) {
      open = false;
    }
  }

  function handleContentClick(event: MouseEvent) {
    event.stopPropagation();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="modal-overlay"
    role="dialog"
    aria-modal="true"
    aria-labelledby={title ? 'modal-title' : undefined}
    tabindex="-1"
    onclick={handleBackdropClick}
    transition:fade={{ duration: 150 }}
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="card-standard {sizeClasses[size]} w-full max-h-[90vh] flex flex-col"
      onclick={handleContentClick}
      onkeydown={(e) => e.stopPropagation()}
      transition:scale={{ duration: 200, start: 0.95 }}
    >
      <!-- Header -->
      {#if title || showCloseButton}
        <div class="flex items-center justify-between mb-4">
          {#if title}
            <h3 id="modal-title" class="text-lg font-heading font-semibold text-contrast">
              {title}
            </h3>
          {:else}
            <div></div>
          {/if}
          
          {#if showCloseButton}
            <button
              onclick={() => open = false}
              class="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
              aria-label="Close modal"
            >
              <X class="h-5 w-5" />
            </button>
          {/if}
        </div>
      {/if}

      <!-- Content -->
      <div class="flex-1 overflow-y-auto">
        {@render children?.()}
      </div>

      <!-- Footer -->
      {#if footer}
        <div class="mt-6 flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
          {@render footer?.()}
        </div>
      {/if}
    </div>
  </div>
{/if}

