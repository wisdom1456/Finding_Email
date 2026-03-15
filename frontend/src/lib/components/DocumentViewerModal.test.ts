import { render, screen, fireEvent } from '@testing-library/svelte';
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
				download: () => Promise.resolve({ data: new Blob(['test']), error: null }),
			}),
		},
	};
}

describe('DocumentViewerModal', () => {
	it('renders modal when document provided', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc(),
				documents: [makeDoc()],
				supabaseClient: makeSupabaseClient(),
				onclose: vi.fn(),
			},
		});
		const dialog = document.querySelector('[role="dialog"]');
		expect(dialog).toBeTruthy();
	});

	it('shows document name in header', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc(),
				documents: [makeDoc()],
				supabaseClient: makeSupabaseClient(),
				onclose: vi.fn(),
			},
		});
		expect(screen.getByText('Contract.pdf')).toBeTruthy();
	});

	it('renders tab navigation', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc(),
				documents: [makeDoc()],
				supabaseClient: makeSupabaseClient(),
				onclose: vi.fn(),
			},
		});
		expect(screen.getByText('Preview')).toBeTruthy();
		expect(screen.getByText('Summary')).toBeTruthy();
		expect(screen.getByText('Raw Text')).toBeTruthy();
	});

	it('shows close button in footer', () => {
		render(DocumentViewerModal, {
			props: {
				document: makeDoc(),
				documents: [makeDoc()],
				supabaseClient: makeSupabaseClient(),
				onclose: vi.fn(),
			},
		});
		const closeButtons = screen.getAllByText('Close');
		expect(closeButtons.length).toBeGreaterThanOrEqual(1);
		// Footer close button is a <button>, sr-only is a <span>
		const footerClose = closeButtons.find(el => el.tagName === 'BUTTON');
		expect(footerClose).toBeTruthy();
	});

	it('does not render when document is null', () => {
		render(DocumentViewerModal, {
			props: {
				document: null,
				documents: [],
				supabaseClient: makeSupabaseClient(),
				onclose: vi.fn(),
			},
		});
		const dialog = document.querySelector('[role="dialog"]');
		expect(dialog).toBeNull();
	});
});
