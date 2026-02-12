<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements';

  let {
    id,
    label,
    type = 'text',
    value = $bindable(),
    error,
    helper,
    required = false,
    placeholder,
    autocomplete,
    disabled = false,
    class: className = '',
    containerClass = '',
    ...restProps
  }: {
    id: string;
    label?: string;
    type?: string;
    value: string;
    error?: string;
    helper?: string;
    required?: boolean;
    placeholder?: string;
    autocomplete?: HTMLInputAttributes['autocomplete'];
    disabled?: boolean;
    class?: string;
    containerClass?: string;
    [key: string]: any;
  } = $props();

  // Generate IDs for ARIA relationships
  const errorId = $derived(error ? `${id}-error` : undefined);
  const helperId = $derived(helper ? `${id}-helper` : undefined);

  // Combine aria-describedby for both error and helper
  const ariaDescribedby = $derived(
    [errorId, helperId].filter(Boolean).join(' ') || undefined
  );

  const inputClasses = $derived(
    `input-standard focus:ring-2 focus:ring-accent focus:border-transparent transition-colors ${className}`
  );
</script>

<div class={containerClass}>
  {#if label}
    <label for={id} class="block text-sm font-medium text-contrast mb-1">
      {label}
      {#if required}
        <span class="text-red-600 ml-0.5" aria-label="required">*</span>
      {/if}
    </label>
  {/if}

  <input
    {id}
    {type}
    {placeholder}
    {autocomplete}
    {required}
    {disabled}
    bind:value={value}
    class={inputClasses}
    aria-invalid={error ? 'true' : 'false'}
    aria-describedby={ariaDescribedby}
    {...restProps}
  />

  {#if helper && !error}
    <p id={helperId} class="mt-1.5 text-xs text-gray-500">
      {helper}
    </p>
  {/if}

  {#if error}
    <p id={errorId} class="mt-1.5 text-xs text-red-600" role="alert">
      {error}
    </p>
  {/if}
</div>
