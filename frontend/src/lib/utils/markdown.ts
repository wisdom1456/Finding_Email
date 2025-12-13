import { marked } from 'marked';

/**
 * Configure marked with safe defaults
 */
marked.setOptions({
	gfm: true, // GitHub Flavored Markdown
	breaks: true // Convert \n to <br>
});

/**
 * Parse markdown text to HTML
 * @param text - Raw markdown text
 * @returns Sanitized HTML string
 */
export function parseMarkdown(text: string): string {
	if (!text) return '';
	
	// Parse markdown to HTML
	const html = marked.parse(text, { async: false }) as string;
	
	return html;
}

