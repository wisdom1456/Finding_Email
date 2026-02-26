import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import SignatureReviewPanel from './SignatureReviewPanel.svelte';

const mockDoc = {
    id: 'doc-123',
    file_name: 'Purchase_Agreement.pdf',
    metadata: {
        signature_detection: { status: 'not_detected', signature_expected: true, indicators: [] }
    }
};

describe('SignatureReviewPanel', () => {
    it('does not render when closed', () => {
        render(SignatureReviewPanel, {
            props: {
                open: false,
                documents: [mockDoc],
                currentIndex: 0,
                caseId: 'case-123',
                onClose: vi.fn(),
                onVerdictSaved: vi.fn(),
                onNavigate: vi.fn()
            }
        });
        expect(screen.queryByText('Signature Review')).toBeNull();
    });

    it('renders document name and progress when open', () => {
        render(SignatureReviewPanel, {
            props: {
                open: true,
                documents: [mockDoc, { ...mockDoc, id: 'doc-456', file_name: 'Contract.pdf' }],
                currentIndex: 0,
                caseId: 'case-123',
                onClose: vi.fn(),
                onVerdictSaved: vi.fn(),
                onNavigate: vi.fn()
            }
        });
        expect(screen.getByText('Signature Review')).toBeTruthy();
        // Should show progress
        const text = document.body.textContent || '';
        expect(text).toContain('1');
        expect(text).toContain('2');
    });

    it('shows Signed, Concern, and No Signature buttons', () => {
        render(SignatureReviewPanel, {
            props: {
                open: true,
                documents: [mockDoc],
                currentIndex: 0,
                caseId: 'case-123',
                onClose: vi.fn(),
                onVerdictSaved: vi.fn(),
                onNavigate: vi.fn()
            }
        });
        expect(screen.getByText(/signed/i)).toBeTruthy();
        expect(screen.getByText(/concern/i)).toBeTruthy();
        expect(screen.getByText(/no signature/i)).toBeTruthy();
    });
});
