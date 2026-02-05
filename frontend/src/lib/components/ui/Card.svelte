<!--
  Card - Reusable card container component

  A wrapper component that provides consistent card styling across the application.
  Encapsulates the .card-standard pattern (white background, rounded corners, shadow, padding).

  Features:
  - Consistent white background with subtle shadow
  - 8px border radius (var(--radius-card))
  - 24px padding (1.5rem) by default
  - Optional hover effect with lift animation
  - Optional click handler with keyboard support
  - Fully accessible when interactive

  Props:
  - hover?: boolean - Enable hover lift effect (default: false)
  - class?: string - Additional CSS classes (can override padding)
  - onclick?: (event: MouseEvent) => void - Click handler
    Note: When onclick is provided, card becomes keyboard-navigable

  Default Styling:
    - background: white
    - border-radius: 8px
    - box-shadow: 0 2px 8px rgba(24, 26, 49, 0.08)
    - padding: 1.5rem (24px)

  Usage:
    Basic card - Wrap content with Card component and children

    Hoverable card - Use hover prop for lift effect on hover

    Interactive card - Add onclick handler with hover for full interaction

    Custom padding - Override default with class="p-8" or other spacing

    No padding - Use class="p-0" for custom internal layouts

  Examples:
    - Dashboard stats: Card with hover prop, includes icons and metrics
    - Modal content: Card with class="max-w-md" for centered display
    - Auth forms: Card component wrapping login/register forms
-->
<script lang="ts">
	let {
		hover = false,
		class: className = '',
		children,
		onclick
	}: {
		hover?: boolean;
		class?: string;
		children?: any;
		onclick?: (event: MouseEvent) => void;
	} = $props();

	const baseClasses = 'card-standard';
	const hoverClasses = hover ? 'card-hover cursor-pointer' : '';
	const classes = $derived(`${baseClasses} ${hoverClasses} ${className}`);
</script>

{#if onclick}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		class={classes}
		{onclick}
		role="button"
		tabindex="0"
		onkeydown={(e) => {
			if (e.key === 'Enter' || e.key === ' ') {
				e.preventDefault();
				onclick?.(e as unknown as MouseEvent);
			}
		}}
	>
		{@render children?.()}
	</div>
{:else}
	<div class={classes}>
		{@render children?.()}
	</div>
{/if}
