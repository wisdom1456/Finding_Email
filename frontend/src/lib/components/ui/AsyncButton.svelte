<!--
	AsyncButton - Button with built-in loading state management
	
	Features:
	- Automatic loading state
	- Prevents multiple clicks
	- Shows spinner during operation
	- Cursor changes to 'wait'
	- Maintains all standard button props
-->
<script lang="ts">
	import { Loader2 } from 'lucide-svelte';
	
	// Props
	let {
		onclick,
		disabled = false,
		loading = $bindable(false),
		loadingText = 'Loading...',
		variant = 'primary', // 'primary' | 'secondary' | 'danger' | 'ghost'
		size = 'default', // 'sm' | 'default' | 'lg'
		class: className = '',
		children,
		...restProps
	}: {
		onclick?: (event: MouseEvent) => void | Promise<void>;
		disabled?: boolean;
		loading?: boolean;
		loadingText?: string;
		variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
		size?: 'sm' | 'default' | 'lg';
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
	
	// Variant styles
	const variantClasses = {
		primary: 'bg-accent hover:bg-accent-hover text-white',
		secondary: 'bg-white hover:bg-gray-50 text-gray-700 border border-gray-300',
		danger: 'bg-red-600 hover:bg-red-700 text-white',
		ghost: 'bg-transparent hover:bg-gray-100 text-gray-700'
	};
	
	// Size styles
	const sizeClasses = {
		sm: 'px-3 py-1.5 text-xs',
		default: 'px-4 py-2 text-sm',
		lg: 'px-6 py-3 text-base'
	};
	
	const baseClasses = 'inline-flex items-center justify-center font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent disabled:opacity-50 disabled:cursor-not-allowed';
	const loadingCursor = isLoading ? 'cursor-wait' : '';
	
	const buttonClasses = `${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${loadingCursor} ${className}`;
</script>

<button
	onclick={handleClick}
	disabled={isDisabled}
	class={buttonClasses}
	{...restProps}
>
	{#if isLoading || loading}
		<Loader2 class="h-4 w-4 mr-2 animate-spin" />
		{loadingText}
	{:else}
		{@render children()}
	{/if}
</button>

<style>
	/* Ensure cursor changes immediately */
	button.cursor-wait,
	button.cursor-wait * {
		cursor: wait !important;
	}
</style>

