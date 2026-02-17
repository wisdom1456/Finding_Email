export type ParsedSSEEvent = Record<string, unknown>;

/**
 * Incremental SSE parser that safely handles arbitrary chunk fragmentation.
 */
export class SSEEventParser {
	private carry = '';

	push(chunk: string): ParsedSSEEvent[] {
		if (!chunk) return [];
		this.carry += chunk;

		const events: ParsedSSEEvent[] = [];
		let separatorIndex = this.carry.indexOf('\n\n');

		while (separatorIndex >= 0) {
			const rawEvent = this.carry.slice(0, separatorIndex);
			this.carry = this.carry.slice(separatorIndex + 2);
			separatorIndex = this.carry.indexOf('\n\n');

			const parsed = this.parseEvent(rawEvent);
			if (parsed) {
				events.push(parsed);
			}
		}

		return events;
	}

	reset(): void {
		this.carry = '';
	}

	private parseEvent(rawEvent: string): ParsedSSEEvent | null {
		if (!rawEvent.trim()) return null;

		const dataLines: string[] = [];
		const lines = rawEvent.split('\n');
		for (const line of lines) {
			if (line.startsWith(':')) continue;
			if (!line.startsWith('data:')) continue;
			dataLines.push(line.slice(5).trimStart());
		}

		if (dataLines.length === 0) return null;
		const payload = dataLines.join('\n');
		if (!payload) return null;

		try {
			const parsed = JSON.parse(payload);
			if (parsed && typeof parsed === 'object') {
				return parsed as ParsedSSEEvent;
			}
			return null;
		} catch {
			return null;
		}
	}
}
