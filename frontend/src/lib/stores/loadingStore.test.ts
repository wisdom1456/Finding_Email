import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { loadingStore, withLoading } from './loadingStore';

describe('loadingStore', () => {
	beforeEach(() => {
		loadingStore.stop();
	});

	it('starts in idle state', () => {
		const state = get(loadingStore);
		expect(state.isLoading).toBe(false);
		expect(state.operation).toBeNull();
		expect(state.message).toBeNull();
	});

	it('start sets loading state with operation name', () => {
		loadingStore.start('upload');
		const state = get(loadingStore);
		expect(state.isLoading).toBe(true);
		expect(state.operation).toBe('upload');
		expect(state.message).toBeNull();
	});

	it('start accepts optional message', () => {
		loadingStore.start('analyze', 'Processing documents...');
		const state = get(loadingStore);
		expect(state.message).toBe('Processing documents...');
	});

	it('stop resets to idle state', () => {
		loadingStore.start('upload');
		loadingStore.stop();
		const state = get(loadingStore);
		expect(state.isLoading).toBe(false);
		expect(state.operation).toBeNull();
		expect(state.message).toBeNull();
	});

	it('start sets cursor to wait on document body', () => {
		loadingStore.start('upload');
		expect(document.body.style.cursor).toBe('wait');
	});

	it('stop resets cursor', () => {
		loadingStore.start('upload');
		loadingStore.stop();
		expect(document.body.style.cursor).toBe('');
	});

	it('isOperationLoading returns true for active operation', () => {
		loadingStore.start('delete');
		expect(loadingStore.isOperationLoading('delete')).toBe(true);
	});

	it('isOperationLoading returns false for different operation', () => {
		loadingStore.start('delete');
		expect(loadingStore.isOperationLoading('upload')).toBe(false);
	});

	it('isOperationLoading returns false when idle', () => {
		expect(loadingStore.isOperationLoading('anything')).toBe(false);
	});
});

describe('withLoading', () => {
	beforeEach(() => {
		loadingStore.stop();
	});

	it('sets loading during async operation and returns result', async () => {
		const result = await withLoading('test-op', async () => {
			expect(get(loadingStore).isLoading).toBe(true);
			expect(get(loadingStore).operation).toBe('test-op');
			return 42;
		});
		expect(result).toBe(42);
		expect(get(loadingStore).isLoading).toBe(false);
	});

	it('passes message through', async () => {
		await withLoading('test-op', async () => {
			expect(get(loadingStore).message).toBe('Please wait...');
		}, 'Please wait...');
	});

	it('stops loading even on error', async () => {
		await expect(
			withLoading('failing-op', async () => {
				throw new Error('boom');
			})
		).rejects.toThrow('boom');

		expect(get(loadingStore).isLoading).toBe(false);
	});
});
