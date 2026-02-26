import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import DocumentRelationships from './DocumentRelationships.svelte';

describe('DocumentRelationships', () => {
    const relationships = [
        { related_doc_id: 'doc-456', relationship_type: 'modifies', related_doc_name: 'Contract_Main.pdf' }
    ];
    const availableDocs = [
        { id: 'doc-456', name: 'Contract_Main.pdf' },
        { id: 'doc-789', name: 'Inspection_Report.pdf' },
    ];

    it('renders existing relationships', () => {
        render(DocumentRelationships, {
            props: {
                documentId: 'doc-123',
                relationships,
                availableDocuments: availableDocs,
                onAddRelationship: vi.fn(),
                onRemoveRelationship: vi.fn()
            }
        });
        expect(screen.getByText(/Contract_Main/i)).toBeTruthy();
        expect(screen.getByText(/modifies/i)).toBeTruthy();
    });

    it('calls onRemoveRelationship when X clicked', async () => {
        const onRemove = vi.fn();
        render(DocumentRelationships, {
            props: {
                documentId: 'doc-123',
                relationships,
                availableDocuments: availableDocs,
                onAddRelationship: vi.fn(),
                onRemoveRelationship: onRemove
            }
        });
        const removeBtn = document.querySelector('[data-remove="doc-456"]') as HTMLButtonElement;
        if (removeBtn) await fireEvent.click(removeBtn);
        expect(onRemove).toHaveBeenCalledWith('doc-456');
    });
});
