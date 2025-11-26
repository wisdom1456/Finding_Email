<script lang="ts">
	/**
	 * Toast notification component for displaying temporary messages
	 * Supports success, error, warning, and info variants
	 */

	import { X, CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-svelte';

	type ToastType = 'success' | 'error' | 'warning' | 'info';

	interface Props {
		type?: ToastType;
		message: string;
		duration?: number;
		onClose: () => void;
	}

	let { type = 'info', message, duration = 5000, onClose }: Props = $props();

	// Auto-dismiss after duration
	$effect(() => {
		if (duration > 0) {
			const timer = setTimeout(onClose, duration);
			return () => clearTimeout(timer);
		}
	});

	const styles: Record<ToastType, { bg: string; border: string; iconColor: string }> = {
		success: {
			bg: 'bg-accent/10',
			border: 'border-accent',
			iconColor: 'text-accent'
		},
		error: {
			bg: 'bg-red-50',
			border: 'border-red-400',
			iconColor: 'text-red-500'
		},
		warning: {
			bg: 'bg-amber-50',
			border: 'border-amber-400',
			iconColor: 'text-amber-500'
		},
		info: {
			bg: 'bg-contrast-light/10',
			border: 'border-contrast-light',
			iconColor: 'text-contrast-light'
		}
	};

	const style = $derived(styles[type]);
</script>

<div
	class="fixed bottom-4 right-4 z-50 animate-slide-up max-w-sm"
	role="alert"
	aria-live="polite"
>
	<div
		class="flex items-start gap-3 p-4 rounded-lg shadow-dropdown border-l-4 bg-white {style.border}"
	>
		<span class="flex-shrink-0 {style.iconColor}">
			{#if type === 'success'}
				<CheckCircle class="h-5 w-5" />
			{:else if type === 'error'}
				<XCircle class="h-5 w-5" />
			{:else if type === 'warning'}
				<AlertTriangle class="h-5 w-5" />
			{:else}
				<Info class="h-5 w-5" />
			{/if}
		</span>
		<p class="text-sm text-contrast flex-1">{message}</p>
		<button
			onclick={onClose}
			class="flex-shrink-0 text-gray-400 hover:text-gray-600 transition-colors"
			aria-label="Dismiss"
		>
			<X class="h-4 w-4" />
		</button>
	</div>
</div>

<style>
	@keyframes slide-up {
		from {
			transform: translateY(100%);
			opacity: 0;
		}
		to {
			transform: translateY(0);
			opacity: 1;
		}
	}

	.animate-slide-up {
		animation: slide-up 0.3s ease-out;
	}
</style>
