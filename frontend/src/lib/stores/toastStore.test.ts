import { describe, it, expect, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { toastStore } from './toastStore';

// Mock crypto.randomUUID
let uuidCounter = 0;
vi.stubGlobal('crypto', {
	randomUUID: () => `uuid-${++uuidCounter}`,
});

describe('toastStore', () => {
	beforeEach(() => {
		toastStore.clear();
		uuidCounter = 0;
	});

	it('starts with an empty array', () => {
		expect(get(toastStore)).toEqual([]);
	});

	it('adds a success toast with default duration', () => {
		toastStore.success('Saved');
		const toasts = get(toastStore);
		expect(toasts).toHaveLength(1);
		expect(toasts[0]).toMatchObject({
			type: 'success',
			message: 'Saved',
			duration: 5000,
		});
	});

	it('adds an error toast with 8000ms default duration', () => {
		toastStore.error('Something broke');
		const toasts = get(toastStore);
		expect(toasts).toHaveLength(1);
		expect(toasts[0]).toMatchObject({
			type: 'error',
			message: 'Something broke',
			duration: 8000,
		});
	});

	it('adds warning and info toasts with 5000ms default', () => {
		toastStore.warning('Watch out');
		toastStore.info('FYI');
		const toasts = get(toastStore);
		expect(toasts).toHaveLength(2);
		expect(toasts[0].type).toBe('warning');
		expect(toasts[0].duration).toBe(5000);
		expect(toasts[1].type).toBe('info');
		expect(toasts[1].duration).toBe(5000);
	});

	it('respects custom duration', () => {
		toastStore.success('Quick', 1000);
		expect(get(toastStore)[0].duration).toBe(1000);
	});

	it('respects custom duration on error toast', () => {
		toastStore.error('Slow error', 15000);
		expect(get(toastStore)[0].duration).toBe(15000);
	});

	it('assigns unique IDs to each toast', () => {
		toastStore.success('First');
		toastStore.success('Second');
		const toasts = get(toastStore);
		expect(toasts[0].id).not.toBe(toasts[1].id);
	});

	it('removes a specific toast by ID', () => {
		toastStore.success('Keep');
		const id = toastStore.error('Remove me');
		toastStore.success('Also keep');

		toastStore.remove(id);
		const toasts = get(toastStore);
		expect(toasts).toHaveLength(2);
		expect(toasts.every(t => t.message !== 'Remove me')).toBe(true);
	});

	it('clear removes all toasts', () => {
		toastStore.success('One');
		toastStore.error('Two');
		toastStore.warning('Three');
		expect(get(toastStore)).toHaveLength(3);

		toastStore.clear();
		expect(get(toastStore)).toEqual([]);
	});

	it('remove is a no-op for non-existent ID', () => {
		toastStore.success('Exists');
		toastStore.remove('non-existent');
		expect(get(toastStore)).toHaveLength(1);
	});
});
