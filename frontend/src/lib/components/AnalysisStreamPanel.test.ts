import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

// We test the save-before-complete logic by extracting the key behavioral contract:
// 1. onComplete is called only AFTER saveAnalysis resolves
// 2. onComplete is called even if saveAnalysis fails

describe('AnalysisStreamPanel save timing', () => {
	let mockFetch: ReturnType<typeof vi.fn<typeof fetch>>;

	beforeEach(() => {
		mockFetch = vi.fn<typeof fetch>();
		vi.stubGlobal('fetch', mockFetch);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('onComplete called after save resolves', async () => {
		// Track call order
		const callOrder: string[] = [];
		let resolveSave!: () => void;
		const savePromise = new Promise<void>((resolve) => {
			resolveSave = resolve;
		});

		// Mock fetch to return a delayed response for the save endpoint
		mockFetch.mockImplementation((url: string | URL | Request) => {
			if (typeof url === 'string' && url.includes('/save')) {
				callOrder.push('save-started');
				return savePromise.then(() => {
					callOrder.push('save-resolved');
					return new Response(JSON.stringify({ success: true }), { status: 200 });
				});
			}
			return Promise.resolve(new Response('{}', { status: 200 }));
		});

		const { testEmitComplete } = await import('./AnalysisStreamPanel.testutil');

		let completeResolve!: () => void;
		const completePromise = new Promise<void>((resolve) => {
			completeResolve = resolve;
		});

		const onComplete = () => {
			callOrder.push('onComplete');
			completeResolve();
		};

		// Start emitComplete (it will await the save)
		const emitPromise = testEmitComplete('test-case-id', 'analysis content', onComplete, mockFetch);

		// Give the event loop a tick — save started but not resolved
		await new Promise((r) => setTimeout(r, 0));
		expect(callOrder).toContain('save-started');
		expect(callOrder).not.toContain('onComplete');

		// Now resolve the save
		resolveSave();
		await emitPromise;

		// onComplete should be called AFTER save resolved
		const saveIndex = callOrder.indexOf('save-resolved');
		const completeIndex = callOrder.indexOf('onComplete');
		expect(saveIndex).toBeGreaterThanOrEqual(0);
		expect(completeIndex).toBeGreaterThanOrEqual(0);
		expect(saveIndex).toBeLessThan(completeIndex);
	});

	it('onComplete called even if save fails', async () => {
		// Mock fetch to reject for the save endpoint
		mockFetch.mockImplementation((url: string | URL | Request) => {
			if (typeof url === 'string' && url.includes('/save')) {
				return Promise.reject(new Error('Network error'));
			}
			return Promise.resolve(new Response('{}', { status: 200 }));
		});

		const { testEmitComplete } = await import('./AnalysisStreamPanel.testutil');

		let completeCalled = false;
		const onComplete = () => {
			completeCalled = true;
		};

		await testEmitComplete('test-case-id', 'analysis content', onComplete, mockFetch);

		// onComplete should still be called even though save failed
		expect(completeCalled).toBe(true);
	});
});
