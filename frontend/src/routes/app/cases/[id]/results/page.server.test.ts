import { describe, expect, it } from 'vitest';
import { load } from './+page.server';

describe('results compatibility route', () => {
	it('redirects to unified analysis workspace URL', async () => {
		await expect(
			load({
				params: { id: 'case-123' }
			} as any)
		).rejects.toMatchObject({
			status: 307,
			location: '/app/cases/case-123?tab=analysis&view=results'
		});
	});
});
