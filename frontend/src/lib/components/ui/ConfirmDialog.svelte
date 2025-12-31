<!--
  ConfirmDialog - Confirmation modal for destructive actions
  
  Replaces native confirm() dialogs with a branded, accessible modal.
  
  Usage:
  <ConfirmDialog
    bind:open={showConfirm}
    title="Delete Case"
    message="Are you sure you want to delete this case?"
    confirmText="Delete"
    variant="danger"
    onConfirm={handleDelete}
  />
-->
<script lang="ts">
  import { fade, scale } from 'svelte/transition';
  import { AlertTriangle, Trash2, X, Info } from 'lucide-svelte';
  import AsyncButton from './AsyncButton.svelte';

  type Variant = 'danger' | 'warning' | 'info';

  let {
    open = $bindable(false),
    title = 'Confirm',
    message = 'Are you sure you want to continue?',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    variant = 'danger',
    loading = false,
    onConfirm,
    onCancel
  }: {
    open?: boolean;
    title?: string;
    message?: string;
    confirmText?: string;
    cancelText?: string;
    variant?: Variant;
    loading?: boolean;
    onConfirm?: () => void | Promise<void>;
    onCancel?: () => void;
  } = $props();

  const variantConfig: Record<Variant, { icon: typeof AlertTriangle; iconBg: string; iconColor: string; btnVariant: 'danger' | 'primary' | 'secondary' }> = {
    danger: {
      icon: Trash2,
      iconBg: 'bg-red-100',
      iconColor: 'text-red-600',
      btnVariant: 'danger'
    },
    warning: {
      icon: AlertTriangle,
      iconBg: 'bg-amber-100',
      iconColor: 'text-amber-600',
      btnVariant: 'primary'
    },
    info: {
      icon: Info,
      iconBg: 'bg-contrast-light/10',
      iconColor: 'text-contrast-light',
      btnVariant: 'primary'
    }
  };

  const config = $derived(variantConfig[variant]);
  const IconComponent = $derived(config.icon);

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      handleCancel();
    }
  }

  function handleCancel() {
    open = false;
    onCancel?.();
  }

  async function handleConfirm() {
    await onConfirm?.();
    open = false;
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="modal-overlay"
    role="alertdialog"
    aria-modal="true"
    aria-labelledby="confirm-title"
    aria-describedby="confirm-message"
    tabindex="-1"
    onclick={handleCancel}
    transition:fade={{ duration: 150 }}
  >
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="card-standard max-w-md w-full"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      transition:scale={{ duration: 200, start: 0.95 }}
    >
      <div class="flex items-start gap-4">
        <!-- Icon -->
        <div class="flex-shrink-0 p-3 rounded-full {config.iconBg}">
          <IconComponent class="h-6 w-6 {config.iconColor}" />
        </div>

        <!-- Content -->
        <div class="flex-1 min-w-0">
          <h3 id="confirm-title" class="text-lg font-heading font-semibold text-contrast">
            {title}
          </h3>
          <p id="confirm-message" class="mt-2 text-sm text-gray-600">
            {message}
          </p>
        </div>

        <!-- Close button -->
        <button
          onclick={handleCancel}
          class="flex-shrink-0 p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-md transition-colors"
          aria-label="Close"
        >
          <X class="h-5 w-5" />
        </button>
      </div>

      <!-- Actions -->
      <div class="mt-6 flex items-center justify-end gap-3">
        <button
          onclick={handleCancel}
          class="btn btn-secondary"
          disabled={loading}
        >
          {cancelText}
        </button>
        <AsyncButton
          onclick={handleConfirm}
          variant={config.btnVariant}
          loading={loading}
          loadingText="Processing..."
        >
          {confirmText}
        </AsyncButton>
      </div>
    </div>
  </div>
{/if}

