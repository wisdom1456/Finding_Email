import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import DocumentCard from './DocumentCard.svelte';

function makeDoc(overrides: Record<string, any> = {}) {
    return {
        id: 'doc-123',
        file_name: 'Purchase_Agreement.pdf',
        file_type: 'application/pdf',
        file_size: 102400,
        status: 'needs_review',
        document_type_label: null,
        signature_expected: false,
        signed_status: null,
        extracted_text: 'Sample text for testing',
        manual_text: null,
        extracted_at: '2025-01-01T00:00:00Z',
        extraction_quality: 'high',
        is_verified: false,
        is_flagged_as_junk: false,
        storage_path: 'user-1/case-1/doc.pdf',
        metadata: {
            quality_score: 7,
            registry: {},
            attorney_enrichment: {},
        },
        ...overrides,
    };
}

describe('DocumentCard', () => {
    // ── Basic Rendering ──

    it('renders the document filename', () => {
        render(DocumentCard, { props: { doc: makeDoc() } });
        expect(screen.getByText(/Purchase_Agreement/i)).toBeTruthy();
    });

    it('shows type override dropdown when onTypeOverride provided', () => {
        render(DocumentCard, { props: { doc: makeDoc(), onTypeOverride: vi.fn() } });
        const selects = document.querySelectorAll('select');
        expect(selects.length).toBeGreaterThan(0);
    });

    // ── Status Badge Rendering ──

    it('renders "Ready" badge for ready status', () => {
        render(DocumentCard, { props: { doc: makeDoc({ status: 'ready' }) } });
        const badge = document.querySelector('[data-testid="doc-status-badge"]');
        expect(badge?.textContent?.trim()).toBe('Ready');
    });

    it('renders "Needs Review" badge for needs_review status', () => {
        render(DocumentCard, { props: { doc: makeDoc({ status: 'needs_review' }) } });
        const badge = document.querySelector('[data-testid="doc-status-badge"]');
        expect(badge?.textContent?.trim()).toBe('Needs Review');
    });

    it('renders "Extraction Failed" badge for extraction_failed status', () => {
        render(DocumentCard, { props: { doc: makeDoc({ status: 'extraction_failed' }) } });
        const badge = document.querySelector('[data-testid="doc-status-badge"]');
        expect(badge?.textContent?.trim()).toBe('Extraction Failed');
    });

    it('renders "Download Failed" badge for download_failed status', () => {
        render(DocumentCard, { props: { doc: makeDoc({ status: 'download_failed' }) } });
        const badge = document.querySelector('[data-testid="doc-status-badge"]');
        expect(badge?.textContent?.trim()).toBe('Download Failed');
    });

    it('renders "Corrupted" badge for corrupted status', () => {
        render(DocumentCard, { props: { doc: makeDoc({ status: 'corrupted' }) } });
        const badge = document.querySelector('[data-testid="doc-status-badge"]');
        expect(badge?.textContent?.trim()).toBe('Corrupted');
    });

    // ── Action Button Gating by Status ──

    it('shows verify button for needs_review with extracted text', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'needs_review', extracted_text: 'Some text' }), onVerify: vi.fn() },
        });
        const btn = document.querySelector('[data-testid="verify-btn"]');
        expect(btn).toBeTruthy();
        expect((btn as HTMLButtonElement).disabled).toBe(false);
    });

    it('shows disabled verify button when no extracted text', () => {
        render(DocumentCard, {
            props: {
                doc: makeDoc({ status: 'needs_review', extracted_text: null, manual_text: null }),
                onVerify: vi.fn(),
            },
        });
        const btn = document.querySelector('[data-testid="verify-btn"]') as HTMLButtonElement;
        expect(btn).toBeTruthy();
        expect(btn.disabled).toBe(true);
        expect(btn.title).toMatch(/OCR first/i);
    });

    it('does not show verify button for extraction_failed status', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'extraction_failed' }), onVerify: vi.fn() },
        });
        expect(document.querySelector('[data-testid="verify-btn"]')).toBeNull();
    });

    it('does not show verify button for ready status', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'ready' }), onVerify: vi.fn() },
        });
        expect(document.querySelector('[data-testid="verify-btn"]')).toBeNull();
    });

    it('shows re-extract button only for extraction_failed', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'extraction_failed' }), onReExtract: vi.fn() },
        });
        expect(document.querySelector('[data-testid="re-extract-btn"]')).toBeTruthy();
    });

    it('does not show re-extract button for needs_review', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'needs_review' }), onReExtract: vi.fn() },
        });
        expect(document.querySelector('[data-testid="re-extract-btn"]')).toBeNull();
    });

    it('shows re-upload button for download_failed', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'download_failed' }), onReplace: vi.fn() },
        });
        expect(document.querySelector('[data-testid="re-upload-btn"]')).toBeTruthy();
    });

    it('shows re-upload button for corrupted', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'corrupted' }), onReplace: vi.fn() },
        });
        expect(document.querySelector('[data-testid="re-upload-btn"]')).toBeTruthy();
    });

    it('does not show re-upload button for needs_review', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'needs_review' }), onReplace: vi.fn() },
        });
        expect(document.querySelector('[data-testid="re-upload-btn"]')).toBeNull();
    });

    it('shows view/edit button for ready status', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'ready' }), onEdit: vi.fn() },
        });
        const btn = document.querySelector('[data-testid="view-edit-btn"]');
        expect(btn).toBeTruthy();
        expect(btn?.textContent).toMatch(/View\/Edit/);
    });

    it('shows "Review Text" for needs_review status', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'needs_review' }), onEdit: vi.fn() },
        });
        const btn = document.querySelector('[data-testid="view-edit-btn"]');
        expect(btn).toBeTruthy();
        expect(btn?.textContent).toMatch(/Review Text/);
    });

    it('does not show view/edit button for download_failed', () => {
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'download_failed' }), onEdit: vi.fn() },
        });
        expect(document.querySelector('[data-testid="view-edit-btn"]')).toBeNull();
    });

    // ── Callback Invocation ──

    it('calls onVerify with doc ID when verify clicked', async () => {
        const onVerify = vi.fn();
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'needs_review', extracted_text: 'text' }), onVerify },
        });
        const btn = document.querySelector('[data-testid="verify-btn"]')!;
        await fireEvent.click(btn);
        expect(onVerify).toHaveBeenCalledWith('doc-123');
    });

    it('calls onReExtract with doc ID when re-extract clicked', async () => {
        const onReExtract = vi.fn();
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'extraction_failed' }), onReExtract },
        });
        const btn = document.querySelector('[data-testid="re-extract-btn"]')!;
        await fireEvent.click(btn);
        expect(onReExtract).toHaveBeenCalledWith('doc-123');
    });

    it('calls onReplace with doc ID when re-upload clicked', async () => {
        const onReplace = vi.fn();
        render(DocumentCard, {
            props: { doc: makeDoc({ status: 'download_failed' }), onReplace },
        });
        const btn = document.querySelector('[data-testid="re-upload-btn"]')!;
        await fireEvent.click(btn);
        expect(onReplace).toHaveBeenCalledWith('doc-123');
    });

    // ── data-testid and data-doc-status ──

    it('sets data-testid="document-card" on root', () => {
        render(DocumentCard, { props: { doc: makeDoc() } });
        expect(document.querySelector('[data-testid="document-card"]')).toBeTruthy();
    });

    it('sets data-doc-status attribute matching doc status', () => {
        render(DocumentCard, { props: { doc: makeDoc({ status: 'corrupted' }) } });
        const card = document.querySelector('[data-testid="document-card"]');
        expect(card?.getAttribute('data-doc-status')).toBe('corrupted');
    });
});
