import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { tick } from 'svelte';
import DocumentViewerModal from './DocumentViewerModal.svelte';

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn().mockResolvedValue({ session: { access_token: 'test' }, user: { id: 'user-1' } }),
}));

vi.mock('$lib/stores/toastStore', () => ({
	toastStore: { success: vi.fn(), error: vi.fn() },
}));

// PDF classification (the sibling test file mocks these to text-like)
vi.mock('$lib/utils/documentClassification', () => ({
	isPdfLikeDocument: () => true,
	isImageLikeDocument: () => false,
	isTextLikeDocument: () => false,
}));

vi.mock('$lib/utils/formatters', () => ({
	formatFileSize: (size: number) => `${Math.round(size / 1024)} KB`,
}));

function makePdfDoc(overrides: Record<string, any> = {}) {
	return {
		id: 'doc-pdf-1',
		file_name: 'Contract.pdf',
		file_type: 'application/pdf',
		file_size: 102400,
		storage_path: 'user-1/case-1/contract.pdf',
		extracted_at: '2025-01-01T00:00:00Z',
		metadata: {},
		...overrides,
	};
}

function makeSupabaseClient() {
	return {
		from: () => ({
			select: () => ({
				eq: () => ({
					single: () => Promise.resolve({ data: { extracted_text: 'Sample text' }, error: null }),
				}),
			}),
		}),
		storage: {
			from: () => ({
				download: () => Promise.resolve({ data: new Blob(['%PDF-1.4']), error: null }),
			}),
		},
	};
}

describe('DocumentViewerModal PDF preview', () => {
	beforeEach(() => {
		let counter = 0;
		globalThis.URL.createObjectURL = vi.fn(() => `blob:mock-${++counter}`);
		globalThis.URL.revokeObjectURL = vi.fn();
	});

	it('shows the on-demand hint with a load button before loading', async () => {
		render(DocumentViewerModal, {
			props: {
				document: makePdfDoc(),
				documents: [makePdfDoc()],
				supabaseClient: makeSupabaseClient(),
				onclose: vi.fn(),
			},
		});
		await tick();
		expect(screen.getByText(/loaded on demand/i)).toBeTruthy();
		expect(screen.getByRole('button', { name: 'Load PDF Preview' })).toBeTruthy();
	});

	it('keeps the PDF preview visible after Load PDF Preview is clicked (no reset flash)', async () => {
		const { container } = render(DocumentViewerModal, {
			props: {
				document: makePdfDoc(),
				documents: [makePdfDoc()],
				supabaseClient: makeSupabaseClient(),
				onclose: vi.fn(),
			},
		});
		await tick();

		await fireEvent.click(screen.getByRole('button', { name: 'Load PDF Preview' }));

		// Let the async download + state updates settle
		await waitFor(() => {
			expect(container.querySelector('object[type="application/pdf"]')).toBeTruthy();
		});

		// Give any (buggy) effect re-runs a chance to reset state
		await tick();
		await new Promise((r) => setTimeout(r, 0));
		await tick();

		// The preview must still be mounted, not reverted to the hint
		expect(container.querySelector('object[type="application/pdf"]')).toBeTruthy();
		expect(screen.queryByText(/loaded on demand/i)).toBeNull();
		// And the blob URL created for it must not have been revoked
		expect(globalThis.URL.revokeObjectURL).not.toHaveBeenCalled();
	});
});
