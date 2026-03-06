import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import TriageDashboard from './TriageDashboard.svelte';

describe('TriageDashboard', () => {
    const signedDoc = {
        id: '1', status: 'ready', file_name: 'contract.pdf',
        signature_expected: true, signed_status: 'signed',
        document_type_label: 'Contract',
        metadata: { quality_score: 9 },
    };
    const unsignedDoc = {
        id: '2', status: 'needs_review', file_name: 'agreement.pdf',
        signature_expected: true, signed_status: 'not_detected',
        metadata: { quality_score: 3 },
    };

    it('shows all-clear message when all docs are ready and signed', () => {
        render(TriageDashboard, { props: { documents: [signedDoc], activeFilters: new Set<string>(), onFilterToggle: vi.fn() } });
        expect(screen.getByText(/verified and ready/i)).toBeTruthy();
    });

    it('shows attention count when problems exist', () => {
        render(TriageDashboard, { props: { documents: [signedDoc, unsignedDoc], activeFilters: new Set<string>(), onFilterToggle: vi.fn() } });
        // Should show some indication of attention needed
        const text = document.body.textContent || '';
        expect(text.toLowerCase()).toContain('attention');
    });
});
