const WHITESPACE_RE = /\s+/g;
const EXTENSION_RE = /\.[a-z0-9]{1,10}$/i;
const TRAILING_PARENS_RE = /\s*\([^)]*\)\s*$/;

export function normalizeBlacklistText(value: string): string {
	if (!value) return '';

	return value
		.toLowerCase()
		.replace(/[_-]/g, ' ')
		.replace(WHITESPACE_RE, ' ')
		.trim();
}

export function stripFileExtension(value: string): string {
	if (!value) return '';
	return value.replace(EXTENSION_RE, '').trim();
}

export function toCanonicalBlacklistTerm(value: string): string {
	let canonical = normalizeBlacklistText(stripFileExtension(value));
	if (!canonical) return '';

	let previous = '';
	while (canonical && canonical !== previous) {
		previous = canonical;
		canonical = canonical.replace(TRAILING_PARENS_RE, '').trim();
	}

	return canonical.replace(/^[-_:;,. ]+|[-_:;,. ]+$/g, '');
}

function termVariants(value: string): string[] {
	const variants = [
		normalizeBlacklistText(value),
		normalizeBlacklistText(stripFileExtension(value)),
		toCanonicalBlacklistTerm(value)
	].filter(Boolean);

	return [...new Set(variants)];
}

export function deriveBlacklistRule(value: string): string {
	const canonical = toCanonicalBlacklistTerm(value);
	return canonical || normalizeBlacklistText(stripFileExtension(value));
}

export function isNameBlacklisted(name: string, blacklist: string[]): boolean {
	if (!name || !blacklist?.length) return false;

	const normalizedName = normalizeBlacklistText(name);
	const normalizedNameNoExt = normalizeBlacklistText(stripFileExtension(name));
	const canonicalName = toCanonicalBlacklistTerm(name);

	for (const rule of blacklist) {
		if (!rule) continue;

		for (const variant of termVariants(rule)) {
			if (
				normalizedName.startsWith(variant) ||
				normalizedNameNoExt.startsWith(variant) ||
				(canonicalName && canonicalName.startsWith(variant))
			) {
				return true;
			}
		}
	}

	return false;
}

