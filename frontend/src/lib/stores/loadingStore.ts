/**
 * Global Loading State Management
 * 
 * Provides centralized loading state with automatic cursor management
 * and loading indicators for async operations.
 */

import { writable } from 'svelte/store';

interface LoadingState {
	isLoading: boolean;
	operation: string | null;
	message: string | null;
}

function createLoadingStore() {
	const { subscribe, set, update } = writable<LoadingState>({
		isLoading: false,
		operation: null,
		message: null
	});

	return {
		subscribe,
		
		/**
		 * Start a loading operation
		 * Automatically sets cursor to 'wait' on document body
		 */
		start: (operation: string, message?: string) => {
			update(state => {
				// Add loading cursor to body
				if (!state.isLoading) {
					document.body.style.cursor = 'wait';
				}
				
				return {
					isLoading: true,
					operation,
					message: message || null
				};
			});
		},
		
		/**
		 * Stop the loading operation
		 * Removes loading cursor from document body
		 */
		stop: () => {
			update(state => {
				// Remove loading cursor
				document.body.style.cursor = '';
				
				return {
					isLoading: false,
					operation: null,
					message: null
				};
			});
		},
		
		/**
		 * Check if a specific operation is currently loading
		 */
		isOperationLoading: (operation: string): boolean => {
			let current: LoadingState;
			subscribe(value => current = value)();
			return current!.isLoading && current!.operation === operation;
		}
	};
}

export const loadingStore = createLoadingStore();

/**
 * Decorator for async functions to automatically manage loading state
 * 
 * @example
 * const deleteCase = withLoading('delete-case', async () => {
 *   await api.delete('/cases/123');
 * });
 */
export async function withLoading<T>(
	operation: string,
	fn: () => Promise<T>,
	message?: string
): Promise<T> {
	try {
		loadingStore.start(operation, message);
		const result = await fn();
		return result;
	} finally {
		loadingStore.stop();
	}
}

