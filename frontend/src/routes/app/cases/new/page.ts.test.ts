/**
 * Tests for the +page.ts load function on the New Case page.
 *
 * Goal: kill the jurisdiction race. Previously the page had
 *   let jurisdiction = $state('Florida')
 * and then loaded the profile asynchronously in onMount — so a
 * fast-clicker could create a case with the wrong jurisdiction
 * silently set to Florida.
 *
 * The load function MUST:
 *   - Return the user's default_jurisdiction when set on the profile
 *   - Return '' (empty) when the user has no profile or it lacks a default
 *   - Return '' when the profile fetch fails (no silent Florida fallback)
 */

import { describe, it, expect, vi } from 'vitest';
import { load } from './+page';

function mockFetch(response: { ok: boolean; data?: any }): typeof fetch {
	return vi.fn().mockResolvedValue({
		ok: response.ok,
		json: async () => response.data ?? {}
	}) as unknown as typeof fetch;
}

describe('cases/new/+page.ts load', () => {
	it('returns the profile default_jurisdiction when set', async () => {
		const result = await load({
			fetch: mockFetch({
				ok: true,
				data: { default_jurisdiction: 'New Mexico' }
			})
		} as any);
		expect(result).toEqual({ defaultJurisdiction: 'New Mexico' });
	});

	it('returns empty string when profile has no default_jurisdiction', async () => {
		const result = await load({
			fetch: mockFetch({
				ok: true,
				data: { full_name: 'Test' } // no default_jurisdiction
			})
		} as any);
		expect(result).toEqual({ defaultJurisdiction: '' });
	});

	it('returns empty string when profile fetch fails (no Florida fallback)', async () => {
		const result = await load({
			fetch: mockFetch({ ok: false })
		} as any);
		expect(result).toEqual({ defaultJurisdiction: '' });
	});

	it('returns empty string when fetch throws (network error)', async () => {
		const result = await load({
			fetch: vi.fn().mockRejectedValue(new Error('Network'))
		} as any);
		expect(result).toEqual({ defaultJurisdiction: '' });
	});

	it('returns empty string for Florida-shaped null/undefined profile', async () => {
		// Critical: we MUST NOT silently default to Florida even when
		// the profile is present but jurisdiction is explicitly null.
		const result = await load({
			fetch: mockFetch({
				ok: true,
				data: { default_jurisdiction: null }
			})
		} as any);
		expect(result).toEqual({ defaultJurisdiction: '' });
	});
});
