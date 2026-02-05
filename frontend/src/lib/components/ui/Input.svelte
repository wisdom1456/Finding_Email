<!--
  Input - Reusable input field component with label and error handling

  A wrapper component that provides consistent input styling with integrated label,
  error messages, and accessibility features across the application.

  Features:
  - Integrated label with proper htmlFor association
  - Error state with aria-invalid and aria-describedby
  - Helper text support
  - Full accessibility (WCAG AA compliant)
  - Consistent styling via .input-standard
  - Support for all input types
  - Optional required indicator

  Props:
  - id: string - Required unique identifier for the input
  - label?: string - Label text (if not provided, you must add your own label)
  - type?: string - Input type (default: 'text')
  - value: string - Bound value (use bind:value)
  - error?: string - Error message to display
  - helper?: string - Helper text to display below input
  - required?: boolean - Mark field as required
  - placeholder?: string - Placeholder text
  - autocomplete?: string - Autocomplete attribute
  - disabled?: boolean - Disable input
  - class?: string - Additional CSS classes for the input element
  - containerClass?: string - Additional CSS classes for the container

  Usage:
    Basic input with label:
      <Input id="email" label="Email Address" type="email"
        bind:value={email} placeholder="you@example.com" />

    With error message:
      <Input id="password" label="Password" type="password"
        bind:value={password} error={passwordError} required />

    With helper text:
      <Input id="username" label="Username" bind:value={username}
        helper="Choose a unique username (3-20 characters)" />

    Minimal (no label, custom styling):
      <Input id="search" type="search" bind:value={searchQuery}
        placeholder="Search..." class="bg-gray-50" />

  Examples:
    - Login form: Input with id="email", label="Email", type="email", bound to email state
    - Registration: Input with id="password", label="Password", type="password", marked required
    - Search: Input with id="search", type="search", bound to query state

  Note: This component uses Svelte 5 runes ($props, $derived) and requires bind:value for two-way binding.
-->
<script lang="ts">
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
    autocomplete?: string;
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
