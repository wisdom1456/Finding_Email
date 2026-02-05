<script lang="ts">
	import { parseMarkdown } from '$lib/utils/markdown';

	let { content }: { content: string } = $props();

	// Parse the markdown to identify sections
	let parsedHtml = $derived(parseMarkdown(content));
</script>

<div class="full-analysis-container">
	<!-- Decorative header -->
	<div class="analysis-header">
		<div class="header-ornament"></div>
		<h1 class="analysis-title">Comprehensive Legal Analysis</h1>
		<div class="header-ornament"></div>
	</div>

	<!-- Main content with enhanced styling -->
	<article class="analysis-content">
		{@html parsedHtml}
	</article>

	<!-- Footer ornament -->
	<div class="analysis-footer">
		<div class="footer-line"></div>
		<div class="footer-mark">✦</div>
		<div class="footer-line"></div>
	</div>
</div>

<style>
	@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

	.full-analysis-container {
		background: linear-gradient(to bottom, #fafaf9 0%, #ffffff 100%);
		border-radius: 16px;
		padding: 3.5rem 0;
		position: relative;
		overflow: hidden;
	}

	/* Subtle texture overlay */
	.full-analysis-container::before {
		content: '';
		position: absolute;
		inset: 0;
		background-image:
			repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.01) 2px, rgba(0,0,0,0.01) 4px);
		pointer-events: none;
	}

	/* Header styling */
	.analysis-header {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 2rem;
		margin-bottom: 4rem;
		padding: 0 3rem;
	}

	.header-ornament {
		height: 1px;
		flex: 1;
		background: linear-gradient(to right, transparent, #d4d4d8, transparent);
		max-width: 120px;
	}

	.analysis-title {
		font-family: 'Playfair Display', serif;
		font-size: 2.5rem;
		font-weight: 600;
		color: #18181b;
		letter-spacing: -0.025em;
		text-align: center;
		margin: 0;
		white-space: nowrap;
	}

	/* Main content area */
	.analysis-content {
		max-width: 48rem;
		margin: 0 auto;
		padding: 0 3rem;
		font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
		font-size: 1.0625rem;
		line-height: 1.8;
		color: #27272a;
		position: relative;
		z-index: 1;
	}

	/* Typography hierarchy */
	:global(.analysis-content h1) {
		font-family: 'Playfair Display', serif;
		font-size: 2.25rem;
		font-weight: 700;
		color: #18181b;
		margin: 3.5rem 0 1.5rem;
		line-height: 1.2;
		letter-spacing: -0.025em;
		border-bottom: 3px solid #18181b;
		padding-bottom: 0.75rem;
	}

	:global(.analysis-content h1:first-child) {
		margin-top: 0;
	}

	:global(.analysis-content h2) {
		font-family: 'Playfair Display', serif;
		font-size: 1.875rem;
		font-weight: 600;
		color: #18181b;
		margin: 3rem 0 1.25rem;
		line-height: 1.3;
		letter-spacing: -0.02em;
		position: relative;
		padding-left: 1.5rem;
	}

	:global(.analysis-content h2::before) {
		content: '';
		position: absolute;
		left: 0;
		top: 0.5rem;
		width: 4px;
		height: calc(100% - 1rem);
		background: linear-gradient(to bottom, #18181b, #71717a);
		border-radius: 2px;
	}

	:global(.analysis-content h3) {
		font-family: 'IBM Plex Sans', sans-serif;
		font-size: 1.375rem;
		font-weight: 600;
		color: #27272a;
		margin: 2.5rem 0 1rem;
		line-height: 1.4;
		letter-spacing: -0.015em;
	}

	:global(.analysis-content h4) {
		font-family: 'IBM Plex Sans', sans-serif;
		font-size: 1.125rem;
		font-weight: 600;
		color: #3f3f46;
		margin: 2rem 0 0.75rem;
		line-height: 1.5;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		font-size: 0.9375rem;
	}

	/* Paragraphs */
	:global(.analysis-content p) {
		margin: 1.5rem 0;
		color: #3f3f46;
		font-weight: 400;
	}

	:global(.analysis-content p:first-of-type) {
		font-size: 1.1875rem;
		line-height: 1.75;
		color: #27272a;
	}

	/* Lists */
	:global(.analysis-content ul),
	:global(.analysis-content ol) {
		margin: 1.5rem 0;
		padding-left: 2rem;
	}

	:global(.analysis-content li) {
		margin: 0.875rem 0;
		color: #3f3f46;
		line-height: 1.75;
		position: relative;
	}

	:global(.analysis-content ul li) {
		list-style: none;
		padding-left: 1.5rem;
	}

	:global(.analysis-content ul li::before) {
		content: '◆';
		position: absolute;
		left: 0;
		color: #71717a;
		font-size: 0.75rem;
		top: 0.5em;
	}

	:global(.analysis-content ol li) {
		padding-left: 0.5rem;
	}

	:global(.analysis-content li strong) {
		color: #18181b;
		font-weight: 600;
	}

	/* Nested lists */
	:global(.analysis-content li ul),
	:global(.analysis-content li ol) {
		margin: 0.75rem 0;
	}

	/* Strong emphasis */
	:global(.analysis-content strong) {
		color: #18181b;
		font-weight: 600;
	}

	/* Italic emphasis */
	:global(.analysis-content em) {
		font-style: italic;
		color: #52525b;
	}

	/* Blockquotes - styled as pull quotes */
	:global(.analysis-content blockquote) {
		margin: 2.5rem 0;
		padding: 2rem 2.5rem;
		background: #fafaf9;
		border-left: 4px solid #18181b;
		font-family: 'Playfair Display', serif;
		font-size: 1.25rem;
		font-style: italic;
		color: #27272a;
		line-height: 1.6;
		position: relative;
	}

	:global(.analysis-content blockquote::before) {
		content: '"';
		font-size: 4rem;
		color: #d4d4d8;
		position: absolute;
		top: 1rem;
		left: 1rem;
		line-height: 1;
		font-family: 'Playfair Display', serif;
	}

	:global(.analysis-content blockquote p) {
		margin: 0;
		position: relative;
		z-index: 1;
	}

	/* Code blocks */
	:global(.analysis-content pre) {
		background: #18181b;
		color: #fafafa;
		padding: 1.5rem;
		border-radius: 8px;
		overflow-x: auto;
		margin: 2rem 0;
		font-size: 0.9375rem;
		line-height: 1.6;
	}

	:global(.analysis-content code) {
		font-family: 'SF Mono', 'Courier New', monospace;
		font-size: 0.875em;
	}

	:global(.analysis-content p code),
	:global(.analysis-content li code) {
		background: #f4f4f5;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		color: #18181b;
		font-weight: 500;
		border: 1px solid #e4e4e7;
	}

	/* Horizontal rules */
	:global(.analysis-content hr) {
		border: none;
		margin: 3.5rem auto;
		text-align: center;
		position: relative;
		height: 1px;
		background: linear-gradient(to right, transparent, #d4d4d8, transparent);
	}

	:global(.analysis-content hr::after) {
		content: '✦';
		position: absolute;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		background: white;
		padding: 0 1rem;
		color: #a1a1aa;
		font-size: 1rem;
	}

	/* Tables */
	:global(.analysis-content table) {
		width: 100%;
		border-collapse: separate;
		border-spacing: 0;
		margin: 2rem 0;
		border: 1px solid #e4e4e7;
		border-radius: 8px;
		overflow: hidden;
	}

	:global(.analysis-content th) {
		background: #fafaf9;
		padding: 1rem 1.25rem;
		text-align: left;
		font-weight: 600;
		color: #18181b;
		border-bottom: 2px solid #e4e4e7;
		font-size: 0.9375rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	:global(.analysis-content td) {
		padding: 1rem 1.25rem;
		border-bottom: 1px solid #f4f4f5;
		color: #3f3f46;
	}

	:global(.analysis-content tr:last-child td) {
		border-bottom: none;
	}

	:global(.analysis-content tbody tr:hover) {
		background: #fafaf9;
	}

	/* Links */
	:global(.analysis-content a) {
		color: #18181b;
		text-decoration: underline;
		text-decoration-color: #a1a1aa;
		text-decoration-thickness: 1px;
		text-underline-offset: 2px;
		transition: all 0.2s ease;
	}

	:global(.analysis-content a:hover) {
		text-decoration-color: #18181b;
		text-decoration-thickness: 2px;
	}

	/* Footer */
	.analysis-footer {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1.5rem;
		margin-top: 4rem;
		padding: 0 3rem;
	}

	.footer-line {
		height: 1px;
		flex: 1;
		background: linear-gradient(to right, transparent, #d4d4d8, transparent);
		max-width: 150px;
	}

	.footer-mark {
		color: #a1a1aa;
		font-size: 1.25rem;
	}

	/* Responsive design */
	@media (max-width: 768px) {
		.full-analysis-container {
			padding: 2.5rem 0;
		}

		.analysis-header {
			margin-bottom: 3rem;
			padding: 0 1.5rem;
		}

		.analysis-title {
			font-size: 1.875rem;
		}

		.header-ornament {
			max-width: 60px;
		}

		.analysis-content {
			padding: 0 1.5rem;
			font-size: 1rem;
		}

		:global(.analysis-content h1) {
			font-size: 1.875rem;
			margin: 2.5rem 0 1.25rem;
		}

		:global(.analysis-content h2) {
			font-size: 1.5rem;
			margin: 2.5rem 0 1rem;
		}

		:global(.analysis-content h3) {
			font-size: 1.25rem;
		}

		:global(.analysis-content blockquote) {
			padding: 1.5rem;
			font-size: 1.125rem;
			margin: 2rem 0;
		}

		.analysis-footer {
			margin-top: 3rem;
			padding: 0 1.5rem;
		}
	}

	/* Print styles */
	@media print {
		.full-analysis-container {
			background: white;
		}

		.full-analysis-container::before {
			display: none;
		}

		:global(.analysis-content) {
			max-width: 100%;
			font-size: 11pt;
			line-height: 1.6;
		}

		:global(.analysis-content h1) {
			page-break-after: avoid;
		}

		:global(.analysis-content h2),
		:global(.analysis-content h3) {
			page-break-after: avoid;
			page-break-inside: avoid;
		}
	}
</style>
