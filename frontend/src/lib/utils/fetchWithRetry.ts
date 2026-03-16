/**
 * Fetch wrapper with automatic retry on 502/503 and network errors.
 */
export async function fetchWithRetry(
	url: string,
	options: RequestInit,
	retries = 2
): Promise<Response> {
	for (let attempt = 0; attempt <= retries; attempt++) {
		try {
			const response = await fetch(url, options);
			if (response.status === 502 || response.status === 503) {
				if (attempt < retries) {
					console.warn(`[fetchWithRetry] ${response.status} on attempt ${attempt + 1}, retrying...`);
					await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
					continue;
				}
			}
			return response;
		} catch (err) {
			const isNetworkError = err instanceof TypeError && /fetch|network/i.test(err.message);
			if (isNetworkError && attempt < retries) {
				console.warn(`[fetchWithRetry] Network error on attempt ${attempt + 1}, retrying...`, err);
				await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
				continue;
			}
			throw err;
		}
	}
	throw new Error('fetchWithRetry: should not reach here');
}
