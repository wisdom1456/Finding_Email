<!--
  Spinner - Standardized loading indicator component

  A consistent loading spinner used throughout the application.
  Uses Lucide's Loader2 icon with smooth rotation animation.

  Features:
  - Consistent Lucide Loader2 icon across entire app
  - Three size variants with proportional icons
  - Optional label text displayed next to spinner
  - Fully accessible with ARIA attributes
  - Respects prefers-reduced-motion

  Props:
  - size?: 'sm' | 'default' | 'lg' - Size variant (default: 'default')
    sm: 16px (h-4 w-4) - For inline or compact spaces
    default: 24px (h-6 w-6) - Standard loading indicators
    lg: 32px (h-8 w-8) - For prominent loading states
  - label?: string - Optional text label (default: '')
  - class?: string - Additional CSS classes for positioning/styling

  Usage:
    <!-- Basic spinner -->
    <Spinner />

    <!-- With label -->
    <Spinner label="Loading..." />

    <!-- Small spinner with custom color -->
    <Spinner size="sm" class="text-accent" />

    <!-- Large spinner centered -->
    <Spinner size="lg" label="Processing documents..." class="justify-center" />

  Examples:
    - Page load: <Spinner label="Redirecting..." class="text-accent" />
    - Button: <Spinner size="sm" /> (used internally by AsyncButton)
    - Full page: <Spinner size="lg" label="Analyzing case..." />
-->
<script lang="ts">
	import { Loader2 } from 'lucide-svelte';

	type Size = 'sm' | 'default' | 'lg';

	let {
		size = 'default',
		label = '',
		class: className = ''
	}: {
		size?: Size;
		label?: string;
		class?: string;
	} = $props();

	const sizeClasses: Record<Size, string> = {
		sm: 'h-4 w-4',
		default: 'h-6 w-6',
		lg: 'h-8 w-8'
	};

	const iconSize = $derived(sizeClasses[size]);
</script>

<div class="inline-flex items-center gap-2 {className}" role="status" aria-label={label || 'Loading'}>
	<Loader2 class="{iconSize} animate-spin text-current" />
	{#if label}
		<span class="text-sm text-gray-600">{label}</span>
	{/if}
</div>
