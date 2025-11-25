<script lang="ts">
	/**
	 * Toast notification component for displaying temporary messages
	 * Supports success, error, warning, and info variants
	 */

	import { X } from 'lucide-svelte';

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

	const styles: Record<ToastType, { bg: string; icon: string; border: string }> = {
		success: {
			bg: 'bg-green-50',
			icon: '✓',
			border: 'border-green-400'
		},
		error: {
			bg: 'bg-red-50',
			icon: '✕',
			border: 'border-red-400'
		},
		warning: {
			bg: 'bg-amber-50',
			icon: '⚠',
			border: 'border-amber-400'
		},
		info: {
			bg: 'bg-blue-50',
			icon: 'ℹ',
			border: 'border-blue-400'
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
		class="flex items-start gap-3 p-4 rounded-lg shadow-lg border-l-4 {style.bg} {style.border}"
	>
		<span class="text-lg flex-shrink-0">{style.icon}</span>
		<p class="text-sm text-gray-800 flex-1">{message}</p>
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

