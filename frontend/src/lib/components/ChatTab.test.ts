import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, it, expect, vi } from 'vitest';
import ChatTab from './ChatTab.svelte';

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
}));

vi.mock('$lib/stores/toastStore', () => ({
	toastStore: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('$lib/utils/markdown', () => ({
	parseMarkdown: (text: string) => text,
}));

describe('ChatTab', () => {
	it('renders empty state', () => {
		render(ChatTab, { props: { analysisId: 'analysis-1' } });
		const empty = document.querySelector('[data-testid="chat-empty"]');
		expect(empty).toBeTruthy();
		expect(empty?.textContent).toContain('No messages yet');
	});

	it('shows chat input and send button', () => {
		render(ChatTab, { props: { analysisId: 'analysis-1' } });
		const input = document.querySelector('[data-testid="chat-input"]');
		expect(input).toBeTruthy();
		const sendBtn = document.querySelector('[data-testid="chat-send"]');
		expect(sendBtn).toBeTruthy();
	});

	it('disables send when input empty', () => {
		render(ChatTab, { props: { analysisId: 'analysis-1' } });
		const sendBtn = document.querySelector('[data-testid="chat-send"]') as HTMLButtonElement;
		expect(sendBtn.disabled).toBe(true);
	});

	it('renders heading', () => {
		render(ChatTab, { props: { analysisId: 'analysis-1' } });
		expect(screen.getByText('Case Chat Assistant')).toBeTruthy();
	});

	it('shows placeholder text in textarea', () => {
		render(ChatTab, { props: { analysisId: 'analysis-1' } });
		const textarea = document.querySelector('[data-testid="chat-input"]') as HTMLTextAreaElement;
		expect(textarea.placeholder).toContain('Ask a question');
	});

	it('enables send when input has text', async () => {
		render(ChatTab, { props: { analysisId: 'analysis-1' } });
		const textarea = document.querySelector('[data-testid="chat-input"]') as HTMLTextAreaElement;
		await fireEvent.input(textarea, { target: { value: 'Hello' } });
		const sendBtn = document.querySelector('[data-testid="chat-send"]') as HTMLButtonElement;
		expect(sendBtn.disabled).toBe(false);
	});
});
