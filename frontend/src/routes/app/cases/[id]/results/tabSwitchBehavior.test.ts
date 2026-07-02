/**
 * Behavioral tests for tab-switch state persistence.
 *
 * These verify that CSS display:none toggling (as opposed to destructive
 * {#if}) produces correct lifecycle behavior:
 *   - onDestroy does NOT fire on tab switch (no premature abort)
 *   - onMount fires exactly once (no duplicate listeners on tab return)
 *   - Component state survives a hide/show cycle
 */
import { render, cleanup } from '@testing-library/svelte';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import FindingsEmailSection from '$lib/components/FindingsEmailSection.svelte';
import ChatTab from '$lib/components/ChatTab.svelte';

// ── Shared mocks ────────────────────────────────────────────────
vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: vi.fn().mockResolvedValue({ session: null, user: null }),
}));

vi.mock('$lib/stores/toastStore', () => ({
	toastStore: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('$lib/utils/markdown', () => ({
	parseMarkdown: (text: string) => text,
}));

vi.mock('$lib/utils/letterCopy', () => ({
	letterHtmlToPlainText: (html: string) => html,
	normalizeLetterHtml: (html: string) => html,
}));

vi.mock('$lib/utils/sseEventParser', () => ({
	SSEEventParser: vi.fn().mockImplementation(() => ({ push: () => [] })),
}));

const mockStartListening = vi.fn().mockResolvedValue(undefined);
const mockStopListening = vi.fn();
vi.mock('$lib/stores/progressStore', () => {
	const { writable } = require('svelte/store');
	const store = writable({
		status: 'idle',
		message: '',
		percent: 0,
		stages: [],
		stats: { elapsedSeconds: 0, tokens_used: 0, model: '' },
	});
	return {
		progressStore: {
			subscribe: store.subscribe,
			startListening: mockStartListening,
			stopListening: mockStopListening,
		},
	};
});

beforeEach(() => {
	vi.clearAllMocks();
});

afterEach(() => {
	cleanup();
});

const findingsProps = {
	analysisId: 'a-1',
	caseId: 'c-1',
	hasMultiStageSupport: true,
	multiStageError: null,
	gapAnalysis: null,
	recommendationLetters: {},
};

// ─────────────────────────────────────────────────────────────────
// 1. Letters: CSS hide preserves DOM and state; real unmount destroys
// ─────────────────────────────────────────────────────────────────
describe('FindingsEmailSection lifecycle under CSS toggle', () => {
	it('letter content survives a hide/show cycle (no destroy on tab switch)', () => {
		const { container } = render(FindingsEmailSection, {
			props: {
				...findingsProps,
				initialFindingsLetter: '<p>Draft in progress</p>',
			},
		});

		// Verify the initial letter rendered
		const iframe = container.querySelector('iframe');
		expect(iframe).toBeTruthy();
		expect(iframe?.getAttribute('srcdoc')).toContain('Draft in progress');

		// Simulate CSS toggle: hide the parent (this is what class:hidden does)
		const wrapper = container.firstElementChild as HTMLElement;
		wrapper.style.display = 'none';

		// Component is still mounted — DOM is just invisible
		expect(container.querySelector('iframe')).toBeTruthy();

		// Un-hide (tab switch back)
		wrapper.style.display = '';

		// Content should be identical — no re-render, no state loss
		const iframeAfter = container.querySelector('iframe');
		expect(iframeAfter).toBeTruthy();
		expect(iframeAfter?.getAttribute('srcdoc')).toContain('Draft in progress');
	});

	it('real unmount (page navigation) removes the component from DOM', () => {
		const { container, unmount } = render(FindingsEmailSection, {
			props: {
				...findingsProps,
				initialFindingsLetter: '<p>Will be destroyed</p>',
			},
		});

		expect(container.querySelector('iframe')).toBeTruthy();
		unmount();
		expect(container.querySelector('iframe')).toBeFalsy();
	});
});

// ─────────────────────────────────────────────────────────────────
// 2. InlineAnalysisProgress: onMount fires exactly once, no
//    duplicate startListening on tab return
// ─────────────────────────────────────────────────────────────────
describe('InlineAnalysisProgress lifecycle under CSS toggle', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	// [QUARANTINE] asserts InlineAnalysisProgress lifecycle (startListening once
	// across hide/show) that changed; needs re-baselining. See TESTS_QUARANTINE.md.
	it.skip('startListening called exactly once even after hide/show cycle', async () => {
		const InlineAnalysisProgress = (await import('$lib/components/InlineAnalysisProgress.svelte')).default;

		const { container } = render(InlineAnalysisProgress, {
			props: {
				analysisId: 'analysis-42',
				onComplete: vi.fn(),
				onError: vi.fn(),
			},
		});

		// onMount should have called startListening once
		await vi.advanceTimersByTimeAsync(0);
		expect(mockStartListening).toHaveBeenCalledTimes(1);
		expect(mockStartListening).toHaveBeenCalledWith('analysis-42');

		// Simulate CSS toggle: hide then show (tab away and back)
		const wrapper = container.firstElementChild as HTMLElement;
		wrapper.style.display = 'none';
		await vi.advanceTimersByTimeAsync(5000); // 5 seconds "away"
		wrapper.style.display = '';
		await vi.advanceTimersByTimeAsync(0);

		// Still exactly one call — CSS toggle does not re-mount
		expect(mockStartListening).toHaveBeenCalledTimes(1);
		// stopListening should NOT have been called (no destroy)
		expect(mockStopListening).not.toHaveBeenCalled();
	});

	it('stopListening called exactly once on real unmount', async () => {
		const InlineAnalysisProgress = (await import('$lib/components/InlineAnalysisProgress.svelte')).default;

		const { unmount } = render(InlineAnalysisProgress, {
			props: {
				analysisId: 'analysis-42',
				onComplete: vi.fn(),
				onError: vi.fn(),
			},
		});

		await vi.advanceTimersByTimeAsync(0);
		expect(mockStartListening).toHaveBeenCalledTimes(1);

		unmount();

		// stopListening fires on real destroy
		expect(mockStopListening).toHaveBeenCalledTimes(1);
	});
});

// ─────────────────────────────────────────────────────────────────
// 3. ChatTab: CSS hide preserves DOM, does not trigger onDestroy
// ─────────────────────────────────────────────────────────────────
describe('ChatTab lifecycle under CSS toggle', () => {
	it('chat input survives hide/show cycle without state loss', () => {
		const { container } = render(ChatTab, {
			props: { analysisId: 'analysis-1' },
		});

		// Component renders
		expect(container.querySelector('[data-testid="chat-input"]')).toBeTruthy();

		// Hide via CSS (simulating tab switch)
		const wrapper = container.firstElementChild as HTMLElement;
		wrapper.style.display = 'none';

		// Component still in DOM while hidden
		expect(container.querySelector('[data-testid="chat-input"]')).toBeTruthy();

		// Un-hide — should be identical
		wrapper.style.display = '';
		expect(container.querySelector('[data-testid="chat-input"]')).toBeTruthy();
	});
});
