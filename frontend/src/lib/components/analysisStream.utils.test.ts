/**
 * Tests for AnalysisStreamPanel extracted utilities.
 *
 * Validates:
 * - formatTime: edge cases for seconds/minutes formatting
 * - parseSSELine: SSE protocol parsing, JSON extraction, event classification
 * - nextStatus: state machine transitions for stream lifecycle
 */
import { describe, it, expect } from 'vitest';
import { formatTime, parseSSELine, nextStatus, type StreamStatus } from './analysisStream.utils';

// ── formatTime ──

describe('formatTime', () => {
	it('formats seconds only', () => {
		expect(formatTime(0)).toBe('0s');
		expect(formatTime(5)).toBe('5s');
		expect(formatTime(59)).toBe('59s');
	});

	it('formats minutes and seconds', () => {
		expect(formatTime(60)).toBe('1m 0s');
		expect(formatTime(90)).toBe('1m 30s');
		expect(formatTime(125)).toBe('2m 5s');
	});
});

// ── parseSSELine ──

describe('parseSSELine', () => {
	it('returns null for non-data lines', () => {
		expect(parseSSELine('')).toBeNull();
		expect(parseSSELine('event: message')).toBeNull();
		expect(parseSSELine(': comment')).toBeNull();
		expect(parseSSELine('id: 123')).toBeNull();
	});

	it('returns null for empty data payload', () => {
		expect(parseSSELine('data: ')).toBeNull();
		expect(parseSSELine('data:   ')).toBeNull();
	});

	it('returns null for invalid JSON', () => {
		expect(parseSSELine('data: not-json')).toBeNull();
		expect(parseSSELine('data: {broken')).toBeNull();
	});

	it('parses token event', () => {
		const result = parseSSELine('data: {"token":"Hello "}');
		expect(result).toEqual({ type: 'token', token: 'Hello ' });
	});

	it('parses thinking phase event', () => {
		const result = parseSSELine('data: {"phase":"thinking","elapsed":3}');
		expect(result).toEqual({ type: 'thinking', elapsed: 3 });
	});

	it('parses streaming phase event', () => {
		const result = parseSSELine('data: {"phase":"streaming","thinking_time":5}');
		expect(result).toEqual({ type: 'streaming_phase', thinkingTime: 5 });
	});

	it('parses heartbeat event', () => {
		const result = parseSSELine('data: {"heartbeat":1}');
		expect(result).toEqual({ type: 'heartbeat' });
	});

	it('parses done event with scope counts', () => {
		const result = parseSSELine('data: {"done":true,"docs_in_scope":10,"docs_omitted":2}');
		expect(result).toEqual({ type: 'done', docsInScope: 10, docsOmitted: 2 });
	});

	it('parses done event without scope counts', () => {
		const result = parseSSELine('data: {"done":true}');
		expect(result).toEqual({ type: 'done', docsInScope: undefined, docsOmitted: undefined });
	});

	it('parses error event', () => {
		const result = parseSSELine('data: {"error":"Rate limit exceeded"}');
		expect(result).toEqual({ type: 'error', error: 'Rate limit exceeded' });
	});

	it('error takes priority over other fields', () => {
		// If both error and token are present, error wins
		const result = parseSSELine('data: {"error":"fail","token":"data"}');
		expect(result?.type).toBe('error');
	});

	it('returns unknown for unrecognized data', () => {
		const result = parseSSELine('data: {"something":"else"}');
		expect(result).toEqual({ type: 'unknown' });
	});
});

// ── nextStatus ──

describe('nextStatus', () => {
	it('transitions to thinking from idle', () => {
		expect(nextStatus({ type: 'thinking' }, 'idle')).toBe('thinking');
	});

	it('does not re-enter thinking when already thinking', () => {
		expect(nextStatus({ type: 'thinking' }, 'thinking')).toBeNull();
	});

	it('transitions to streaming on streaming_phase event', () => {
		expect(nextStatus({ type: 'streaming_phase' }, 'thinking')).toBe('streaming');
	});

	it('transitions from thinking to streaming when token arrives', () => {
		expect(nextStatus({ type: 'token', token: 'Hi' }, 'thinking')).toBe('streaming');
	});

	it('does not change status when token arrives during streaming', () => {
		expect(nextStatus({ type: 'token', token: 'Hi' }, 'streaming')).toBeNull();
	});

	it('transitions to complete on done event', () => {
		expect(nextStatus({ type: 'done' }, 'streaming')).toBe('complete');
	});

	it('transitions to error on error event', () => {
		expect(nextStatus({ type: 'error', error: 'fail' }, 'streaming')).toBe('error');
		expect(nextStatus({ type: 'error', error: 'fail' }, 'thinking')).toBe('error');
	});

	it('heartbeat does not change status', () => {
		expect(nextStatus({ type: 'heartbeat' }, 'streaming')).toBeNull();
		expect(nextStatus({ type: 'heartbeat' }, 'thinking')).toBeNull();
	});

	it('unknown event does not change status', () => {
		expect(nextStatus({ type: 'unknown' }, 'streaming')).toBeNull();
	});
});
