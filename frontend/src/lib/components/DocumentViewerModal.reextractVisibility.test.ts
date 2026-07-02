import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
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

vi.mock('$lib/utils/documentClassification', () => ({
	isPdfLikeDocument: () => false,
	isImageLikeDocument: () => false,
	isTextLikeDocument: () => true,
}));

vi.mock('$lib/utils/formatters', () => ({
	formatFileSize: (size: number) => `${Math.round(size / 1024)} KB`,
}));

function makeDoc(overrides: Record<string, any> = {}) {
	return {
		id: 'doc-1',
		file_name: 'Contract.pdf',
		file_type: 'application/pdf',
		file_size: 102400,
		storage_path: 'user-1/case-1/contract.pdf',
		status: 'ready',
		extracted_at: '2025-01-01T00:00:00Z',
		extraction_quality: 'high',
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
				download: () => Promise.resolve({ data: new Blob(['test']), error: null }),
			}),
		},
	};
}

describe('DocumentViewerModal re-extract visibility', () => {
	it('hides Re-Extract buttons for a healthy document even when showReextract is true', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc(),
				documents: [makeDoc()],
				supabaseClient: makeSupabaseClient(),
				showReextract: true,
				onclose: vi.fn(),
				onreextract: vi.fn(),
			},
		});
		expect(screen.queryByText(/Re-Extract/)).toBeNull();
	});

	it('shows both Re-Extract buttons when extraction failed', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc({ status: 'extraction_failed' }),
				documents: [makeDoc({ status: 'extraction_failed' })],
				supabaseClient: makeSupabaseClient(),
				showReextract: true,
				onclose: vi.fn(),
				onreextract: vi.fn(),
			},
		});
		expect(screen.getByText('Re-Extract (OCR)')).toBeTruthy();
		expect(screen.getByText('Re-Extract (Vision)')).toBeTruthy();
	});

	it('shows Re-Extract buttons when extraction has not run (extracted_at is null)', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc({ extracted_at: null }),
				documents: [makeDoc({ extracted_at: null })],
				supabaseClient: makeSupabaseClient(),
				showReextract: true,
				onclose: vi.fn(),
				onreextract: vi.fn(),
			},
		});
		expect(screen.getByText('Re-Extract (OCR)')).toBeTruthy();
		expect(screen.getByText('Re-Extract (Vision)')).toBeTruthy();
	});

	it('hides Re-Extract buttons when showReextract is false, regardless of recovery need', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc({ status: 'extraction_failed' }),
				documents: [makeDoc({ status: 'extraction_failed' })],
				supabaseClient: makeSupabaseClient(),
				showReextract: false,
				onclose: vi.fn(),
				onreextract: vi.fn(),
			},
		});
		expect(screen.queryByText(/Re-Extract/)).toBeNull();
	});
});
