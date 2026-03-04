/**
 * Retry wrapper for Supabase queries that handles transient 503 PGRST002 errors.
 *
 * PostgREST returns 503 when its schema cache is being rebuilt (e.g. after DDL
 * changes or cold starts). These resolve within seconds.
 */

const MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;

interface SupabaseResponse<T> {
	data: T | null;
	error: { message: string; code?: string; details?: string; hint?: string } | null;
	status?: number;
	statusText?: string;
}

/**
 * Execute a Supabase query with automatic retry on 503 errors.
 *
 * @example
 * const { data, error } = await withRetry(() =>
 *   supabase.from('documents').select('*').eq('case_id', id)
 * );
 */
export async function withRetry<T>(
	queryFn: () => PromiseLike<SupabaseResponse<T>>,
	maxRetries: number = MAX_RETRIES
): Promise<SupabaseResponse<T>> {
	let lastResult: SupabaseResponse<T> | undefined;

	for (let attempt = 0; attempt <= maxRetries; attempt++) {
		lastResult = await queryFn();

		const is503 =
			lastResult.status === 503 ||
			lastResult.error?.code === 'PGRST002' ||
			lastResult.error?.message?.includes('schema cache');

		if (!is503 || attempt === maxRetries) {
			return lastResult;
		}

		const delay = BASE_DELAY_MS * Math.pow(2, attempt);
		await new Promise((resolve) => setTimeout(resolve, delay));
	}

	return lastResult!;
}
