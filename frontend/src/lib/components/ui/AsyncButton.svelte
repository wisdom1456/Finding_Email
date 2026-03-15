<!--
	AsyncButton - Button with built-in loading state management
	
	Features:
	- Automatic loading state
	- Prevents multiple clicks
	- Shows spinner during operation
	- Cursor changes to 'wait'
	- Uses central design system btn classes
-->
<script lang="ts">
	import { Loader2 } from 'lucide-svelte';
	
	type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
	type Size = 'sm' | 'default' | 'lg';
	
	let {
		onclick,
		disabled = false,
		loading = $bindable(false),
		loadingText = 'Loading...',
		variant = 'primary',
		size = 'default',
		class: className = '',
		children,
		...restProps
	}: {
		onclick?: (event: MouseEvent) => void | Promise<void>;
		disabled?: boolean;
		loading?: boolean;
		loadingText?: string;
		variant?: Variant;
		size?: Size;
		class?: string;
		children?: any;
		[key: string]: any;
	} = $props();
	
	// Internal loading state
	let isLoading = $state(false);
	
	// Combined disabled state
	const isDisabled = $derived(disabled || loading || isLoading);
	
	// Handle async click
	async function handleClick(event: MouseEvent) {
		if (isDisabled || !onclick) return;
		
		isLoading = true;
		loading = true;
		
		try {
			await onclick(event);
		} catch (error) {
			console.error('AsyncButton error:', error);
			throw error;
		} finally {
			isLoading = false;
			loading = false;
		}
	}
	
	// Variant styles - aligned with app.css .btn system
	const variantClasses: Record<Variant, string> = {
		primary: 'btn-primary focus:ring-accent',
		secondary: 'btn-secondary focus:ring-accent',
		danger: 'btn-danger focus:ring-red-500',
		ghost: 'btn-ghost focus:ring-accent'
	};
	
	// Size styles - consistent with design system spacing
	const sizeClasses: Record<Size, string> = {
		sm: 'px-3 py-1.5 text-xs',
		default: 'px-4 py-2 text-sm',
		lg: 'px-5 py-2.5 text-base'
	};
	
	// Icon sizes per button size
	const iconSizeClasses: Record<Size, string> = {
		sm: 'h-3.5 w-3.5',
		default: 'h-4 w-4',
		lg: 'h-5 w-5'
	};
	
	const baseClasses = 'btn inline-flex items-center justify-center font-medium rounded-btn transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed btn-active';
	
	// Use $derived to capture reactive isLoading state
	const buttonClasses = $derived(
		`${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${isLoading ? 'cursor-wait' : ''} ${className}`
	);
</script>

<button
	data-testid="async-button"
	onclick={handleClick}
	disabled={isDisabled}
	class={buttonClasses}
	{...restProps}
>
	{#if isLoading || loading}
		<Loader2 class="{iconSizeClasses[size]} mr-2 animate-spin" />
		{loadingText}
	{:else}
		{@render children?.()}
	{/if}
</button>

