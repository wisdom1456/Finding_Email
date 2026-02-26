import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import DocumentReviewPanel from './DocumentReviewPanel.svelte';

const mockDoc = {
    id: 'doc-123',
    file_name: 'Contract.pdf',
    extracted_text: 'This is the extracted contract text...',
    metadata: {
        extraction_quality: 'high',
        extraction_method: 'Google Cloud Vision',
    }
};

describe('DocumentReviewPanel', () => {
    it('does not render when closed', () => {
        render(DocumentReviewPanel, {
            props: {
                open: false,
                document: mockDoc,
                caseId: 'case-123',
                onClose: vi.fn(),
                onVerify: vi.fn(),
                onReExtract: vi.fn(),
                onTextEdit: vi.fn()
            }
        });
        expect(screen.queryByText(mockDoc.file_name)).toBeNull();
    });

    it('renders document filename when open', () => {
        render(DocumentReviewPanel, {
            props: {
                open: true,
                document: mockDoc,
                caseId: 'case-123',
                onClose: vi.fn(),
                onVerify: vi.fn(),
                onReExtract: vi.fn(),
                onTextEdit: vi.fn()
            }
        });
        expect(screen.getByText('Contract.pdf')).toBeTruthy();
    });

    it('shows extracted text content', () => {
        render(DocumentReviewPanel, {
            props: {
                open: true,
                document: mockDoc,
                caseId: 'case-123',
                onClose: vi.fn(),
                onVerify: vi.fn(),
                onReExtract: vi.fn(),
                onTextEdit: vi.fn()
            }
        });
        expect(screen.getByText(/extracted contract text/i)).toBeTruthy();
    });
});
