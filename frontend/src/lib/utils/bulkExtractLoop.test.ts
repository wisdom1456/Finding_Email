import { describe, it, expect, vi } from 'vitest';
import { runCoverageLoop } from './bulkExtractLoop';

describe('runCoverageLoop', () => {
	it('loops until remaining is 0, accumulating counts (the 54->34->14->0 shrink)', async () => {
		const results = [
			{ extracted_count: 20, failed_count: 0, errors: [], remaining: 34 },
			{ extracted_count: 20, failed_count: 0, errors: [], remaining: 14 },
			{ extracted_count: 12, failed_count: 2, errors: ['x', 'y'], remaining: 0 }
		];
		let i = 0;
		const runBatch = vi.fn(async () => results[i++]);
		const out = await runCoverageLoop(runBatch, () => {}, 10);
		expect(runBatch).toHaveBeenCalledTimes(3);
		expect(out.totalExtracted).toBe(52);
		expect(out.totalFailed).toBe(2);
		expect(out.errors).toEqual(['x', 'y']);
		expect(out.hitCap).toBe(false);
	});

	it('stops at maxBatches and flags hitCap when remaining never reaches 0', async () => {
		const runBatch = vi.fn(async () => ({
			extracted_count: 0,
			failed_count: 1,
			errors: ['stuck'],
			remaining: 5
		}));
		const out = await runCoverageLoop(runBatch, () => {}, 3);
		expect(runBatch).toHaveBeenCalledTimes(3);
		expect(out.hitCap).toBe(true);
	});
});
