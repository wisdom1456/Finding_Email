/**
 * Tests verifying that tab switching uses CSS display:none toggle
 * instead of destructive {#if} rendering, so in-flight state
 * (letter generation, streaming) is preserved across tab switches.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const pagePath = resolve(__dirname, '+page.svelte');
const pageSource = readFileSync(pagePath, 'utf-8');

describe('ResultsWorkspace tab persistence (CSS toggle)', () => {
	it('uses class:hidden for analysis tab instead of {#if}', () => {
		expect(pageSource).toContain("class:hidden={activeTab !== 'analysis'}");
	});

	it('uses class:hidden for gaps tab instead of {#if}', () => {
		expect(pageSource).toContain("class:hidden={activeTab !== 'gaps'}");
	});

	it('uses class:hidden for letters tab instead of {#if}', () => {
		expect(pageSource).toContain("class:hidden={activeTab !== 'letters'}");
	});

	it('uses class:hidden for chat tab instead of {#if}', () => {
		expect(pageSource).toContain("class:hidden={activeTab !== 'chat'}");
	});

	it('uses class:hidden for quality tab instead of {#if}', () => {
		expect(pageSource).toContain("class:hidden={activeTab !== 'quality'}");
	});

	it('does NOT use {:else if} chain for tab content', () => {
		// The old pattern was {:else if activeTab === 'letters'} etc.
		// After the CSS toggle migration, no {:else if activeTab} should remain.
		expect(pageSource).not.toMatch(/\{:else if activeTab ===/);
	});

	it('still uses destructive {#if} for heavy fullAnalysis tab', () => {
		expect(pageSource).toContain("{#if activeTab === 'fullAnalysis'}");
	});

	it('still uses destructive {#if} for heavy documents tab', () => {
		expect(pageSource).toContain("{#if activeTab === 'documents'}");
	});

	it('FindingsEmailSection is inside a CSS-toggled letters div', () => {
		// Verify FindingsEmailSection appears after the letters CSS toggle div
		const lettersToggle = pageSource.indexOf("class:hidden={activeTab !== 'letters'}");
		const findingsSection = pageSource.indexOf('<FindingsEmailSection');
		expect(lettersToggle).toBeGreaterThan(-1);
		expect(findingsSection).toBeGreaterThan(lettersToggle);
	});
});

describe('Main case page streaming panel persistence', () => {
	const mainPagePath = resolve(__dirname, '../+page.svelte');
	const mainPageSource = readFileSync(mainPagePath, 'utf-8');

	it('AnalysisStreamPanel is outside the analysis tab {#if}', () => {
		const streamPanelPos = mainPageSource.indexOf('<AnalysisStreamPanel');
		const analysisTabIf = mainPageSource.indexOf("{#if activeTab === 'analysis'}");
		expect(streamPanelPos).toBeGreaterThan(-1);
		expect(analysisTabIf).toBeGreaterThan(-1);
		// Stream panel should appear BEFORE the analysis tab conditional
		expect(streamPanelPos).toBeLessThan(analysisTabIf);
	});

	it('InlineAnalysisProgress is outside the analysis tab {#if}', () => {
		const progressPos = mainPageSource.indexOf('<InlineAnalysisProgress');
		const analysisTabIf = mainPageSource.indexOf("{#if activeTab === 'analysis'}");
		expect(progressPos).toBeGreaterThan(-1);
		expect(analysisTabIf).toBeGreaterThan(-1);
		expect(progressPos).toBeLessThan(analysisTabIf);
	});

	it('streaming panels use CSS hidden for visibility', () => {
		// The streaming panels should be wrapped in class:hidden divs
		expect(mainPageSource).toContain("class:hidden={activeTab !== 'analysis'} class=\"mb-6 page-spacing\"");
	});
});
