import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/stores/progressStore', async () => {
	const { writable } = await import('svelte/store');
	return { progressStore: writable<any>({ status: 'idle' }) };
});

import ClioImportProgressModal from './ClioImportProgressModal.svelte';
import { progressStore } from '$lib/stores/progressStore';
import type { Writable } from 'svelte/store';

// The real progressStore module type has no `.set` (it's a custom store
// wrapper); the vi.mock factory above swaps in a plain writable at runtime,
// so we assert the type here to match what's actually mounted.
const mockState = progressStore as unknown as Writable<any>;

// The mocked store is a module-level singleton shared across every test in
// this file (vi.mock's factory runs once). Reset it before each test so a
// fresh modal mount doesn't inherit doc_log state left over from a prior
// test — mirrors the real store's reset-on-new-session behavior.
beforeEach(() => {
	mockState.set({ status: 'idle' });
});

function docLog() {
	return [
		{ i: 1, name: 'Lease.pdf', size_bytes: 1048576, outcome: 'imported' },
		{ i: 2, name: 'signature.png', size_bytes: 20480, outcome: 'skipped_small_image' },
		{ i: 3, name: 'Contract.pdf', size_bytes: 2097152, outcome: 'downloading' },
	];
}

describe('ClioImportProgressModal doc log', () => {
	it('renders every doc_log entry with number, name and size', async () => {
		render(ClioImportProgressModal, {
			props: { show: true, onClose: vi.fn() },
		});
		mockState.set({
			status: 'active',
			phase: 'import_documents',
			message: 'Downloading document 3 of 3: Contract.pdf',
			percent: 80,
			current_doc: { index: 3, total: 3, name: 'Contract.pdf' },
			doc_log: docLog(),
		});
		await new Promise((r) => setTimeout(r, 0));
		expect(screen.getByText(/Lease\.pdf/)).toBeTruthy();
		expect(screen.getByText(/1\.0 MB/)).toBeTruthy();
		expect(screen.getByText(/signature\.png/)).toBeTruthy();
		// "Contract.pdf" also appears in the "Current Item" banner (state.current_doc.name),
		// so it legitimately renders twice — assert at least one match rather than a single one.
		expect(screen.getAllByText(/Contract\.pdf/).length).toBeGreaterThan(0);
	});

	it('renders classic message list when doc_log absent', async () => {
		render(ClioImportProgressModal, { props: { show: true, onClose: vi.fn() } });
		mockState.set({
			status: 'active',
			phase: 'import_documents',
			message: 'Downloading document 5 of 9: X',
			percent: 50,
		});
		await new Promise((r) => setTimeout(r, 0));
		expect(screen.getByText(/Downloading document 5 of 9/)).toBeTruthy();
	});
});
