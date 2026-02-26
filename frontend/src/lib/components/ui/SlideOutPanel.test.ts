import { render, screen } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import SlideOutPanel from './SlideOutPanel.svelte';

describe('SlideOutPanel', () => {
    it('renders title when open', () => {
        render(SlideOutPanel, { props: { open: true, title: 'Test Panel', onClose: vi.fn() } });
        expect(screen.getByText('Test Panel')).toBeTruthy();
    });

    it('does not render content when closed', () => {
        render(SlideOutPanel, { props: { open: false, title: 'Test Panel', onClose: vi.fn() } });
        expect(screen.queryByText('Test Panel')).toBeNull();
    });
});
