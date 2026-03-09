import { marked } from 'marked';
import DOMPurify from 'dompurify';

/**
 * Configure marked with safe defaults
 */
marked.setOptions({
	gfm: true, // GitHub Flavored Markdown
	breaks: true // Convert \n to <br>
});

/**
 * Parse markdown text to sanitized HTML.
 * Uses DOMPurify to strip XSS vectors from the rendered output.
 * @param text - Raw markdown text
 * @returns Sanitized HTML string
 */
export function parseMarkdown(text: string): string {
	if (!text) return '';

	try {
		const html = marked.parse(text, { async: false }) as string;
		return DOMPurify.sanitize(html);
	} catch {
		// If marked throws on malformed input, return escaped text
		return DOMPurify.sanitize(text);
	}
}
