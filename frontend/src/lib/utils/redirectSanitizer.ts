/**
 * Validate that a redirect target is a safe internal path.
 * Rejects absolute URLs, protocol-relative URLs, and paths with authority.
 */
export function sanitizeRedirectTarget(target: string): string {
	// Must start with / and not // (protocol-relative)
	if (!target.startsWith('/') || target.startsWith('//')) {
		return '/app';
	}
	// Reject backslash tricks (some browsers treat \ as /)
	if (target.includes('\\')) {
		return '/app';
	}
	// Strip any authority-like patterns (e.g., /\@evil.com)
	try {
		const url = new URL(target, 'http://localhost');
		if (url.hostname !== 'localhost') {
			return '/app';
		}
	} catch {
		return '/app';
	}
	return target;
}
