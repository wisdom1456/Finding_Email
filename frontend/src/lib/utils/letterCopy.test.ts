import { describe, expect, it } from 'vitest';

import { letterHtmlToPlainText, letterHtmlToRichFragment, normalizeLetterHtml } from './letterCopy';

describe('letterCopy utils', () => {
	it('normalizes escaped newlines in stored HTML', () => {
		const input = '<html>\\n<body><p>Hello</p></body>\\n</html>';
		expect(normalizeLetterHtml(input)).toContain('\n<body>');
	});

	it('converts HTML document to plain text for Clio-safe paste', () => {
		const html = `
			<!DOCTYPE html>
			<html>
				<head><title>Findings</title></head>
				<body>
					<h1>Findings Email</h1>
					<p>We reviewed your documents.</p>
					<p>Please send the ledger by Friday.</p>
				</body>
			</html>
		`;

		const text = letterHtmlToPlainText(html);
		expect(text).toContain('Findings Email');
		expect(text).toContain('We reviewed your documents.');
		expect(text).toContain('Please send the ledger by Friday.');
		expect(text).not.toContain('<h1>');
	});

	it('extracts rich HTML fragment from full document wrappers', () => {
		const html = `
			<!DOCTYPE html>
			<html>
				<head><style>p { color: red; }</style></head>
				<body><p>Demand paragraph.</p></body>
			</html>
		`;

		const fragment = letterHtmlToRichFragment(html);
		expect(fragment).toContain('<p>Demand paragraph.</p>');
		expect(fragment).not.toContain('<html');
		expect(fragment).not.toContain('<head');
	});
});
