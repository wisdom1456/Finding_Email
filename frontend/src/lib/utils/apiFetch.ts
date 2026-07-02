import { getApiUrl } from '$lib/config';
import { getSecureSession } from '$lib/supabase';
import { fetchWithRetry } from '$lib/utils/fetchWithRetry';

/**
 * Error thrown by apiFetch for non-2xx responses, carrying a message
 * normalized across the backend's error envelopes.
 */
export class ApiError extends Error {
	status: number;
	body: unknown;

	constructor(status: number, message: string, body: unknown) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.body = body;
	}
}

/**
 * Extract a human-readable message from any of the backend error shapes:
 * - {error, message, context}      (AppError handler / normalized catch-all)
 * - {detail: "..."}                (FastAPI HTTPException)
 * - {detail: {message: "..."}}     (structured detail payloads)
 */
export function parseErrorMessage(body: unknown, fallback: string): string {
	if (body && typeof body === 'object') {
		const obj = body as Record<string, unknown>;
		if (typeof obj.message === 'string' && obj.message) return obj.message;
		if (typeof obj.detail === 'string' && obj.detail) return obj.detail;
		if (obj.detail && typeof obj.detail === 'object') {
			const detail = obj.detail as Record<string, unknown>;
			if (typeof detail.message === 'string' && detail.message) return detail.message;
		}
	}
	return fallback;
}

export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
	/** JSON-serializable request body; sets Content-Type automatically. */
	json?: unknown;
	/** Raw body passthrough (FormData, string, etc.). */
	body?: BodyInit | null;
	/** Retry idempotent requests on 429/502/503 + network errors (default: GET only). */
	retry?: boolean;
	/** Skip attaching the Authorization header (default: false). */
	skipAuth?: boolean;
}

/**
 * Authenticated fetch against the backend API.
 *
 * Centralizes the pattern hand-rolled across ~25 files: resolve base URL,
 * validate the session, attach the bearer token, retry idempotent calls,
 * and normalize error parsing. Do NOT use for SSE/streaming endpoints —
 * those manage their own readers and recovery.
 *
 * @param path - API path beginning with '/' (e.g. '/api/cases')
 * @returns Parsed JSON on 2xx (or null for 204 responses)
 * @throws ApiError with a normalized message on non-2xx
 * @throws Error('Not authenticated') when no valid session exists
 */
export async function apiFetch<T = unknown>(path: string, options: ApiFetchOptions = {}): Promise<T> {
	const { json, retry, skipAuth, headers, ...rest } = options;

	const requestHeaders = new Headers(headers);
	if (!skipAuth) {
		const { session } = await getSecureSession();
		if (!session) {
			throw new Error('Not authenticated');
		}
		requestHeaders.set('Authorization', `Bearer ${session.access_token}`);
	}

	let body = rest.body ?? null;
	if (json !== undefined) {
		requestHeaders.set('Content-Type', 'application/json');
		body = JSON.stringify(json);
	}

	const method = (rest.method ?? 'GET').toUpperCase();
	const shouldRetry = retry ?? method === 'GET';
	const url = `${getApiUrl()}${path}`;
	const init: RequestInit = { ...rest, method, headers: requestHeaders, body };

	const response = shouldRetry ? await fetchWithRetry(url, init) : await fetch(url, init);

	if (!response.ok) {
		let errorBody: unknown = null;
		try {
			errorBody = await response.json();
		} catch {
			// non-JSON error body; fall through to status text
		}
		throw new ApiError(
			response.status,
			parseErrorMessage(errorBody, `Request failed (${response.status})`),
			errorBody
		);
	}

	if (response.status === 204) {
		return null as T;
	}
	return (await response.json()) as T;
}
