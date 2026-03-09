import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { clioStore } from './clioStore';

describe('clioStore', () => {
	beforeEach(() => {
		clioStore.reset();
	});

	it('starts disconnected', () => {
		const state = get(clioStore);
		expect(state.connected).toBe(false);
		expect(state.clioUserId).toBeNull();
		expect(state.expiresAt).toBeNull();
	});

	it('setConnected updates all fields', () => {
		clioStore.setConnected(true, 'user-123', '2025-12-31T23:59:59Z');
		const state = get(clioStore);
		expect(state.connected).toBe(true);
		expect(state.clioUserId).toBe('user-123');
		expect(state.expiresAt).toBe('2025-12-31T23:59:59Z');
	});

	it('setConnected defaults optional params to null', () => {
		clioStore.setConnected(true);
		const state = get(clioStore);
		expect(state.connected).toBe(true);
		expect(state.clioUserId).toBeNull();
		expect(state.expiresAt).toBeNull();
	});

	it('disconnect resets to initial state', () => {
		clioStore.setConnected(true, 'user-123', '2025-12-31');
		clioStore.disconnect();
		const state = get(clioStore);
		expect(state.connected).toBe(false);
		expect(state.clioUserId).toBeNull();
		expect(state.expiresAt).toBeNull();
	});

	it('reset behaves identically to disconnect', () => {
		clioStore.setConnected(true, 'user-456');
		clioStore.reset();
		const state = get(clioStore);
		expect(state.connected).toBe(false);
		expect(state.clioUserId).toBeNull();
	});
});
