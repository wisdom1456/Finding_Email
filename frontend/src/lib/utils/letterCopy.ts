export function normalizeLetterHtml(letterHtml: string): string {
	return (letterHtml || '').replace(/\\n/g, '\n').trim();
}

export function letterHtmlToRichFragment(letterHtml: string): string {
	const normalized = normalizeLetterHtml(letterHtml);
	if (!normalized) return '';

	if (typeof DOMParser !== 'undefined') {
		const doc = new DOMParser().parseFromString(normalized, 'text/html');
		const bodyHtml = (doc.body?.innerHTML || '').trim();
		if (bodyHtml) return bodyHtml;
	}

	return normalized;
}

export function letterHtmlToPlainText(letterHtml: string): string {
	const normalized = normalizeLetterHtml(letterHtml);
	if (!normalized) return '';

	if (typeof DOMParser !== 'undefined') {
		const doc = new DOMParser().parseFromString(normalized, 'text/html');
		const rawText = (doc.body?.textContent || '').replace(/\u00a0/g, ' ');
		return rawText
			.replace(/\r/g, '')
			.replace(/[ \t]+\n/g, '\n')
			.replace(/\n{3,}/g, '\n\n')
			.trim();
	}

	return normalized
		.replace(/<style[\s\S]*?<\/style>/gi, ' ')
		.replace(/<script[\s\S]*?<\/script>/gi, ' ')
		.replace(/<[^>]+>/g, ' ')
		.replace(/&nbsp;/gi, ' ')
		.replace(/&amp;/gi, '&')
		.replace(/\s+/g, ' ')
		.trim();
}
