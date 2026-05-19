/**
 * Canonical profile loading + completeness check for letter generation.
 *
 * The "complete" bar is intentionally loose — we only enforce the two
 * fields that, when missing, cause visibly broken letters:
 *
 *  - `full_name` must contain a space (first AND last name). Without
 *    this, the auto-signup trigger fills full_name with the user's
 *    email address, and gpt-4o then hallucinates a `[Last Name]`
 *    placeholder in the signature.
 *
 *  - `default_jurisdiction` must be set (NM or FL). Without it, the
 *    case-creation form silently defaults to Florida.
 *
 * All other letter-relevant fields (phone, firm_name, firm_address,
 * email_signature, bar_number) fall back to DB defaults that work for
 * the current user base; users can override in Settings if needed.
 */

export interface LetterProfile {
	full_name?: string | null;
	default_jurisdiction?: string | null;
}

export function isProfileCompleteForLetters(profile: LetterProfile | null | undefined): boolean {
	if (!profile) return false;

	const name = (profile.full_name ?? '').trim();
	if (!name) return false;
	// Require at least one whitespace-separated word AFTER the first one.
	// "Ceryn" → false. "Ceryn Riley" → true. "ceryn@brflorida.com" → false
	// (no space). "Ceryn " (trailing space) → false (split yields one word).
	const words = name.split(/\s+/).filter((w) => w.length > 0);
	if (words.length < 2) return false;

	const jurisdiction = (profile.default_jurisdiction ?? '').trim();
	if (!jurisdiction) return false;

	return true;
}
