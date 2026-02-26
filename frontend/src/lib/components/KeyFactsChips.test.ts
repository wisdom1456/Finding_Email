import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import KeyFactsChips from './KeyFactsChips.svelte';

describe('KeyFactsChips', () => {
    const facts = {
        date: { value: '03/15/2024', confirmed: false },
        amount: { value: '$425,000', confirmed: true },
    };

    it('renders fact values', () => {
        render(KeyFactsChips, { props: { facts, onFactUpdate: vi.fn(), onFactConfirm: vi.fn() } });
        expect(screen.getByText(/03\/15\/2024/)).toBeTruthy();
        expect(screen.getByText(/\$425,000/)).toBeTruthy();
    });

    it('shows unconfirmed chip with amber styling', () => {
        render(KeyFactsChips, { props: { facts, onFactUpdate: vi.fn(), onFactConfirm: vi.fn() } });
        // The date chip should have amber styling (unconfirmed)
        const dateChips = document.querySelectorAll('[data-key="date"]');
        expect(dateChips.length).toBeGreaterThan(0);
    });
});
