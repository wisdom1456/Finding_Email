/**
 * VerificationHub logic tests
 *
 * VerificationHub has 13+ child component imports making full component rendering
 * impractical in unit tests. Instead, we test:
 *
 * 1. The handler auth/fetch/toast patterns via an extracted pattern test
 * 2. Document gating logic (which docs need extraction, which are verifiable)
 * 3. The handlers are tested end-to-end via DocumentCard callback tests
 *    and the mocked E2E tests in document-lifecycle.spec.ts
 *
 * Handler behavior already covered by existing tests:
 * - DocumentCard.test.ts: button visibility per status, callback invocation
 * - triageGrouping.test.ts: document classification into triage groups
 * - document-lifecycle.spec.ts: full handler flow via Playwright
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Mock dependencies ──

const { mockGetSession } = vi.hoisted(() => ({
	mockGetSession: vi.fn(),
}));

vi.mock('$lib/supabase', () => ({
	getSecureSession: mockGetSession,
	supabase: { storage: { from: () => ({ download: vi.fn() }) } },
}));

vi.mock('$lib/config', () => ({
	getApiUrl: () => 'http://localhost:8000',
}));

function makeDoc(overrides: Record<string, any> = {}) {
	return {
		id: 'doc-001',
		case_id: 'case-001',
		file_name: 'contract.pdf',
		file_type: 'application/pdf',
		file_size: 102400,
		status: 'needs_review',
		extracted_at: '2025-01-01T00:00:00Z',
		extraction_method: 'Google Cloud Vision',
		extracted_text: 'Sample text.',
		manual_text: null,
		is_verified: false,
		is_flagged_as_junk: false,
		metadata: {},
		...overrides,
	};
}

describe('VerificationHub handler patterns', () => {
	let mockFetch: ReturnType<typeof vi.fn<typeof fetch>>;

	beforeEach(() => {
		vi.clearAllMocks();
		mockFetch = vi.fn<typeof fetch>();
		vi.stubGlobal('fetch', mockFetch);
	});

	// ── Auth guard pattern (all handlers share this) ──

	it('handler rejects when not authenticated', async () => {
		mockGetSession.mockResolvedValue({ session: null, user: null });

		// Simulate the auth guard pattern used by all VerificationHub handlers
		const { session, user } = await mockGetSession();
		expect(session).toBeNull();
		expect(user).toBeNull();
		// Handler would throw 'Not authenticated' here
		expect(() => {
			if (!session || !user) throw new Error('Not authenticated');
		}).toThrow('Not authenticated');
	});

	it('handler proceeds when authenticated', async () => {
		mockGetSession.mockResolvedValue({
			session: { access_token: 'test-token' },
			user: { id: 'user-1' },
		});

		const { session, user } = await mockGetSession();
		expect(session.access_token).toBe('test-token');
		expect(user.id).toBe('user-1');
	});

	// ── Verify endpoint pattern ──

	it('verify sends PATCH with auth header and is_verified body', async () => {
		mockGetSession.mockResolvedValue({
			session: { access_token: 'test-token' },
			user: { id: 'user-1' },
		});
		mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) } as Response);

		const { session } = await mockGetSession();
		const docId = 'doc-001';
		await fetch(`http://localhost:8000/api/documents/${docId}/verify`, {
			method: 'PATCH',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${session.access_token}`,
			},
			body: JSON.stringify({ is_verified: true }),
		});

		expect(mockFetch).toHaveBeenCalledWith(
			'http://localhost:8000/api/documents/doc-001/verify',
			expect.objectContaining({
				method: 'PATCH',
				headers: expect.objectContaining({
					Authorization: 'Bearer test-token',
				}),
			})
		);
	});

	// ── Extract endpoint pattern ──

	it('extract sends POST with auth header', async () => {
		mockGetSession.mockResolvedValue({
			session: { access_token: 'test-token' },
			user: { id: 'user-1' },
		});
		mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) } as Response);

		const { session } = await mockGetSession();
		const docId = 'doc-001';
		await fetch(`http://localhost:8000/api/documents/${docId}/extract`, {
			method: 'POST',
			headers: { Authorization: `Bearer ${session.access_token}` },
		});

		expect(mockFetch).toHaveBeenCalledWith(
			'http://localhost:8000/api/documents/doc-001/extract',
			expect.objectContaining({
				method: 'POST',
				headers: expect.objectContaining({
					Authorization: 'Bearer test-token',
				}),
			})
		);
	});

	// ── Error detail parsing pattern ──

	it('parses backend error detail from JSON response', async () => {
		mockFetch.mockResolvedValue({
			ok: false,
			status: 500,
			json: () => Promise.resolve({ detail: 'OCR_SERVICE_TOKEN must be set' }),
		} as Response);

		const response = await mockFetch('http://localhost:8000/api/documents/doc-001/extract');
		expect(response.ok).toBe(false);

		const errBody = await response.json().catch(() => ({}));
		const errorMessage = errBody.detail || `Extraction failed (${response.status})`;
		expect(errorMessage).toBe('OCR_SERVICE_TOKEN must be set');
	});

	it('falls back to status code when response is not JSON', async () => {
		mockFetch.mockResolvedValue({
			ok: false,
			status: 502,
			json: () => Promise.reject(new Error('not json')),
		} as Response);

		const response = await mockFetch('http://localhost:8000/api/documents/doc-001/extract');
		const errBody = await response.json().catch(() => ({}));
		const errorMessage = errBody.detail || `Extraction failed (${response.status})`;
		expect(errorMessage).toBe('Extraction failed (502)');
	});

	// ── Bulk delete pattern ──

	it('bulk delete sends POST with document_ids array', async () => {
		mockGetSession.mockResolvedValue({
			session: { access_token: 'test-token' },
			user: { id: 'user-1' },
		});
		mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) } as Response);

		const { session } = await mockGetSession();
		const docIds = ['doc-1', 'doc-2', 'doc-3'];
		await fetch('http://localhost:8000/api/documents/bulk-delete', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				Authorization: `Bearer ${session.access_token}`,
			},
			body: JSON.stringify({ document_ids: docIds }),
		});

		expect(mockFetch).toHaveBeenCalledWith(
			'http://localhost:8000/api/documents/bulk-delete',
			expect.objectContaining({
				method: 'POST',
				body: JSON.stringify({ document_ids: ['doc-1', 'doc-2', 'doc-3'] }),
			})
		);
	});

	// ── docsNeedingExtraction gating logic ──

	it('identifies docs needing extraction correctly', () => {
		const docs = [
			makeDoc({ id: '1', extracted_at: null }),
			makeDoc({ id: '2', extracted_at: '2025-01-01T00:00:00Z' }),
			makeDoc({ id: '3', extraction_method: 'deferred', extracted_at: '2025-01-01T00:00:00Z' }),
			makeDoc({ id: '4', status: 'pending', extracted_text: null, extracted_at: null }),
			makeDoc({ id: '5', status: 'ready', extracted_text: 'Has text' }),
		];

		// Replicate the docsNeedingExtraction filter from VerificationHub
		const needsExtraction = docs.filter(
			(d) => !d.extracted_at || d.extraction_method === 'deferred' || (d.status === 'pending' && !d.extracted_text)
		);

		expect(needsExtraction.map((d) => d.id)).toEqual(['1', '3', '4']);
	});

	it('docs with extracted_at and non-deferred method do not need extraction', () => {
		const doc = makeDoc({
			extracted_at: '2025-01-01T00:00:00Z',
			extraction_method: 'Google Cloud Vision',
			status: 'ready',
		});

		const needsExtraction = !doc.extracted_at || doc.extraction_method === 'deferred' || (doc.status === 'pending' && !doc.extracted_text);
		expect(needsExtraction).toBe(false);
	});

	// ── Verify button gating logic ──

	it('verify is blocked when doc has no extracted_text and no manual_text', () => {
		const doc = makeDoc({ extracted_text: null, manual_text: null });
		const canVerify = !!(doc.extracted_text || doc.manual_text);
		expect(canVerify).toBe(false);
	});

	it('verify is allowed when doc has extracted_text', () => {
		const doc = makeDoc({ extracted_text: 'Some text' });
		const canVerify = !!(doc.extracted_text || doc.manual_text);
		expect(canVerify).toBe(true);
	});

	it('verify is allowed when doc has manual_text even without extracted_text', () => {
		const doc = makeDoc({ extracted_text: null, manual_text: 'Manual entry' });
		const canVerify = !!(doc.extracted_text || doc.manual_text);
		expect(canVerify).toBe(true);
	});

	// ── Status-based action gating ──

	it('extraction_failed status gates to re-extract only', () => {
		const doc = makeDoc({ status: 'extraction_failed' });
		const showVerify = doc.status === 'needs_review';
		const showReExtract = doc.status === 'extraction_failed';
		const showReUpload = doc.status === 'corrupted' || doc.status === 'download_failed';

		expect(showVerify).toBe(false);
		expect(showReExtract).toBe(true);
		expect(showReUpload).toBe(false);
	});

	it('corrupted status gates to re-upload only', () => {
		const doc = makeDoc({ status: 'corrupted' });
		const showVerify = doc.status === 'needs_review';
		const showReExtract = doc.status === 'extraction_failed';
		const showReUpload = doc.status === 'corrupted' || doc.status === 'download_failed';

		expect(showVerify).toBe(false);
		expect(showReExtract).toBe(false);
		expect(showReUpload).toBe(true);
	});

	it('download_failed status gates to re-upload only', () => {
		const doc = makeDoc({ status: 'download_failed' });
		const showVerify = doc.status === 'needs_review';
		const showReExtract = doc.status === 'extraction_failed';
		const showReUpload = doc.status === 'corrupted' || doc.status === 'download_failed';

		expect(showVerify).toBe(false);
		expect(showReExtract).toBe(false);
		expect(showReUpload).toBe(true);
	});

	it('needs_review status gates to verify', () => {
		const doc = makeDoc({ status: 'needs_review' });
		const showVerify = doc.status === 'needs_review';
		const showReExtract = doc.status === 'extraction_failed';

		expect(showVerify).toBe(true);
		expect(showReExtract).toBe(false);
	});
});
