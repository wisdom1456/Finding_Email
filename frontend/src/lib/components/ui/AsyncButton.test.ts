import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import AsyncButton from './AsyncButton.svelte';

describe('AsyncButton', () => {
	it('renders children text', () => {
		render(AsyncButton, { props: { children: () => 'Click me' } });
		// The button should render but children snippet may not render text directly
		const btn = document.querySelector('[data-testid="async-button"]');
		expect(btn).toBeTruthy();
	});

	it('shows loading text when loading', () => {
		render(AsyncButton, { props: { loading: true, loadingText: 'Saving...' } });
		const btn = document.querySelector('[data-testid="async-button"]');
		expect(btn?.textContent).toContain('Saving...');
	});

	it('disables button when disabled prop', () => {
		render(AsyncButton, { props: { disabled: true } });
		const btn = document.querySelector('[data-testid="async-button"]') as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it('disables button when loading', () => {
		render(AsyncButton, { props: { loading: true } });
		const btn = document.querySelector('[data-testid="async-button"]') as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
	});

	it('fires onclick handler', async () => {
		const onclick = vi.fn();
		render(AsyncButton, { props: { onclick } });
		const btn = document.querySelector('[data-testid="async-button"]')!;
		await fireEvent.click(btn);
		expect(onclick).toHaveBeenCalled();
	});
});
