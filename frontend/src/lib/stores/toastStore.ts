/**
 * Toast notification store for managing app-wide notifications
 * Usage:
 *   import { toastStore } from '$lib/stores/toastStore';
 *   toastStore.success('File uploaded successfully');
 *   toastStore.error('Failed to upload file');
 */

import { writable } from 'svelte/store';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface Toast {
	id: string;
	type: ToastType;
	message: string;
	duration: number;
}

function createToastStore() {
	const { subscribe, update } = writable<Toast[]>([]);

	function addToast(type: ToastType, message: string, duration = 5000): string {
		const id = crypto.randomUUID();
		update((toasts) => [...toasts, { id, type, message, duration }]);
		return id;
	}

	function removeToast(id: string) {
		update((toasts) => toasts.filter((t) => t.id !== id));
	}

	return {
		subscribe,
		success: (message: string, duration?: number) => addToast('success', message, duration),
		error: (message: string, duration?: number) => addToast('error', message, duration ?? 8000),
		warning: (message: string, duration?: number) => addToast('warning', message, duration),
		info: (message: string, duration?: number) => addToast('info', message, duration),
		remove: removeToast,
		clear: () => update(() => [])
	};
}

export const toastStore = createToastStore();

