import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import DocumentListSection from './DocumentListSection.svelte';

vi.mock('$lib/utils/documentClassification', () => ({
	isCaseSummary: () => false,
	isIntakeForm: () => false,
	isVideoAudioFile: () => false,
}));

vi.mock('$lib/utils/signatureDetection', () => ({
	shouldShowSignatureBadge: () => false,
	getDocumentSignatureBadgeClass: () => '',
	getDocumentSignatureLabel: () => '',
}));

vi.mock('$lib/utils/formatters', () => ({
	formatFileSize: (size: number) => `${Math.round(size / 1024)} KB`,
	getStatusColor: () => 'bg-green-100 text-green-800',
}));

function makeDoc(overrides: Record<string, any> = {}) {
	return {
		id: 'doc-1',
		file_name: 'Contract.pdf',
		file_type: 'application/pdf',
		file_size: 102400,
		status: 'ready',
		created_at: '2025-01-01T00:00:00Z',
		metadata: {},
		...overrides,
	};
}

describe('DocumentListSection', () => {
	it('renders document list', () => {
		render(DocumentListSection, {
			props: { documents: [makeDoc()], onview: vi.fn(), ondelete: vi.fn(), onpromote: vi.fn() },
		});
		const list = document.querySelector('[data-testid="doc-list"]');
		expect(list).toBeTruthy();
		expect(screen.getByText('Contract.pdf')).toBeTruthy();
	});

	it('shows empty state when no docs', () => {
		render(DocumentListSection, {
			props: { documents: [], onview: vi.fn(), ondelete: vi.fn(), onpromote: vi.fn() },
		});
		const empty = document.querySelector('[data-testid="doc-list-empty"]');
		expect(empty).toBeTruthy();
		expect(empty?.textContent).toContain('No documents uploaded yet');
	});

	it('calls onview on document click', async () => {
		const onview = vi.fn();
		const doc = makeDoc();
		render(DocumentListSection, {
			props: { documents: [doc], onview, ondelete: vi.fn(), onpromote: vi.fn() },
		});
		const docName = screen.getByText('Contract.pdf');
		await fireEvent.click(docName);
		expect(onview).toHaveBeenCalled();
	});

	it('displays file type info', () => {
		render(DocumentListSection, {
			props: { documents: [makeDoc()], onview: vi.fn(), ondelete: vi.fn(), onpromote: vi.fn() },
		});
		expect(screen.getByText(/100 KB.*application\/pdf/)).toBeTruthy();
	});

	it('shows document count matching input', () => {
		const docs = [makeDoc(), makeDoc({ id: 'doc-2', file_name: 'Evidence.pdf' })];
		render(DocumentListSection, {
			props: { documents: docs, onview: vi.fn(), ondelete: vi.fn(), onpromote: vi.fn() },
		});
		const items = document.querySelectorAll('li');
		expect(items.length).toBe(2);
	});
});
