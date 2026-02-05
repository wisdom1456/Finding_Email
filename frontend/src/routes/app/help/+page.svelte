<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import PageHeader from '$lib/components/ui/PageHeader.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import AccordionItem from '$lib/components/ui/AccordionItem.svelte';
	import {
		BookOpen,
		FolderOpen,
		Upload,
		Play,
		FileText,
		Briefcase,
		FileCheck,
		Link2,
		Sparkles,
		Mail,
		HelpCircle,
		CheckCircle,
		Clock,
		AlertCircle,
		RefreshCw,
		Scale,
		ChevronRight,
		Library,
		Zap,
		Infinity
	} from 'lucide-svelte';

	const tabs = [
		{ id: 'getting-started', label: 'Getting Started' },
		{ id: 'features', label: 'Features & Guides' },
		{ id: 'faq', label: 'FAQ' }
	];

	let activeTab = $state('getting-started');

	// Support URL hash for deep linking
	onMount(() => {
		const hash = $page.url.hash.replace('#', '');
		if (hash && tabs.some((t) => t.id === hash)) {
			activeTab = hash;
		}
	});

	// Update URL hash when tab changes
	$effect(() => {
		if (typeof window !== 'undefined') {
			const newUrl = new URL(window.location.href);
			newUrl.hash = activeTab;
			window.history.replaceState({}, '', newUrl.toString());
		}
	});
</script>

<svelte:head>
	<title>Help & Documentation | Bernhardt Riley</title>
</svelte:head>

<div class="page-spacing">
	<PageHeader
		title="Help & Documentation"
		subtitle="Learn how to use the Legal Document Analysis Portal"
		breadcrumbs={[{ label: 'Dashboard', href: '/app' }, { label: 'Help' }]}
	/>

	<!-- What's New Banner -->
	<div class="mb-8 overflow-hidden rounded-2xl bg-gradient-to-br from-accent/10 via-accent/5 to-transparent border-2 border-accent/20 shadow-sm">
		<div class="p-6 sm:p-8">
			<div class="flex items-start gap-4">
				<div class="shrink-0 rounded-xl bg-accent p-3 shadow-lg">
					<Zap class="h-6 w-6 text-white" />
				</div>
				<div class="flex-1">
					<h3 class="text-xl font-heading font-bold text-contrast mb-2">What's New</h3>
					<div class="space-y-3">
						<div class="flex items-start gap-3">
							<CheckCircle class="h-5 w-5 text-accent shrink-0 mt-0.5" />
							<div>
								<p class="font-semibold text-contrast">Enhanced Full Analysis Display</p>
								<p class="text-sm text-gray-600 mt-1">
									The Full Analysis tab now features a beautiful magazine-style editorial layout with refined typography,
									elegant visual hierarchy, and enhanced readability. Your comprehensive case narratives are now presented
									in a polished, professional format.
								</p>
							</div>
						</div>
						<div class="flex items-start gap-3">
							<Infinity class="h-5 w-5 text-accent shrink-0 mt-0.5" />
							<div>
								<p class="font-semibold text-contrast">Unlimited Document Import from Clio</p>
								<p class="text-sm text-gray-600 mt-1">
									Import as many documents as you need from your Clio matters. We've removed all pagination limits,
									ensuring you get every document, communication, and note from your connected Clio account.
								</p>
							</div>
						</div>
						<div class="flex items-start gap-3">
							<RefreshCw class="h-5 w-5 text-accent shrink-0 mt-0.5" />
							<div>
								<p class="font-semibold text-contrast">Improved Clio Sync Performance</p>
								<p class="text-sm text-gray-600 mt-1">
									Faster, more reliable Clio synchronization with better error handling and comprehensive pagination
									support. All documents, emails, and notes are now imported with complete accuracy.
								</p>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>

	<div class="help-container">
		<Tabs {tabs} bind:activeTab>
			<!-- Getting Started Tab -->
			{#if activeTab === 'getting-started'}
				<div class="help-content">
					<!-- Welcome Section -->
					<section class="feature-card welcome-card">
						<div class="flex items-start gap-5">
							<div class="feature-icon-large">
								<BookOpen class="h-7 w-7" />
							</div>
							<div class="flex-1">
								<h2 class="feature-heading">
									Welcome to the Legal Document Analysis Portal
								</h2>
								<p class="feature-description">
									This portal helps you analyze legal documents and generate professional findings
									emails using AI-powered analysis. From document upload to client-ready findings letters,
									we streamline your case intake workflow.
								</p>
							</div>
						</div>
					</section>

					<!-- Step by Step Guide -->
					<section class="guide-section">
						<h3 class="section-heading">Quick Start Guide</h3>
						<div class="steps-container">
							<!-- Step 1 -->
							<div class="step-card">
								<div class="step-number">1</div>
								<div class="step-content">
									<div class="step-header">
										<FolderOpen class="h-5 w-5 text-accent" />
										<h4 class="step-title">Create a New Case</h4>
									</div>
									<p class="step-description">
										Click the <strong>"New Case"</strong> button on the Dashboard or Cases page. Enter
										your client's name and an optional reference number (like a matter ID from your practice
										management system).
									</p>
								</div>
							</div>

							<!-- Step 2 -->
							<div class="step-card">
								<div class="step-number">2</div>
								<div class="step-content">
									<div class="step-header">
										<Upload class="h-5 w-5 text-accent" />
										<h4 class="step-title">Upload Documents</h4>
									</div>
									<p class="step-description">
										Upload your case documents including intake forms, contracts, correspondence, and
										supporting evidence. You can drag and drop multiple files at once. Supported
										formats include PDF, DOCX, DOC, images (JPG, PNG), TXT, CSV, and EML files.
									</p>
									<div class="tip-box">
										<p class="tip-text">
											<strong>Tip:</strong> Include your client intake form for best results. The AI
											uses this to understand the case context.
										</p>
									</div>
								</div>
							</div>

							<!-- Step 3 -->
							<div class="step-card">
								<div class="step-number">3</div>
								<div class="step-content">
									<div class="step-header">
										<Play class="h-5 w-5 text-accent" />
										<h4 class="step-title">Start Analysis</h4>
									</div>
									<p class="step-description">
										Once your documents are uploaded, click <strong>"Start Analysis"</strong>. The AI
										will process your documents in multiple stages: extracting text, identifying key
										facts, analyzing legal issues, and generating a comprehensive case analysis.
									</p>
									<div class="note-box">
										<p class="note-text">
											<strong>Note:</strong> Analysis typically takes 2-5 minutes depending on the number
											and complexity of documents. There is no limit on the number of documents you can analyze.
										</p>
									</div>
								</div>
							</div>

							<!-- Step 4 -->
							<div class="step-card">
								<div class="step-number">4</div>
								<div class="step-content">
									<div class="step-header">
										<FileText class="h-5 w-5 text-accent" />
										<h4 class="step-title">Review Results</h4>
									</div>
									<p class="step-description">
										When analysis is complete, review the beautifully formatted Full Analysis, document
										summaries, gap analysis, and case insights. You can verify extracted facts, check citations,
										and explore the comprehensive narrative before generating client deliverables.
									</p>
								</div>
							</div>

							<!-- Step 5 -->
							<div class="step-card">
								<div class="step-number">5</div>
								<div class="step-content">
									<div class="step-header">
										<Mail class="h-5 w-5 text-accent" />
										<h4 class="step-title">Generate & Export Letters</h4>
									</div>
									<p class="step-description">
										Generate your final findings email, demand letters, or recommendation letters with professional formatting.
										All documents include proper citations to source materials and are ready for client delivery or
										further editing.
									</p>
								</div>
							</div>
						</div>
					</section>

					<!-- Supported Document Formats -->
					<section class="formats-section">
						<h3 class="section-heading">Supported Document Formats</h3>
						<div class="formats-grid">
							{#each [{ ext: 'PDF', desc: 'Adobe PDF' }, { ext: 'DOCX', desc: 'Word Document' }, { ext: 'DOC', desc: 'Word (Legacy)' }, { ext: 'TXT', desc: 'Plain Text' }, { ext: 'CSV', desc: 'Spreadsheets' }, { ext: 'JPG/PNG', desc: 'Images (OCR)' }, { ext: 'EML', desc: 'Email Files' }, { ext: 'HTML', desc: 'Web Pages' }] as format}
								<div class="format-card">
									<span class="format-ext">{format.ext}</span>
									<p class="format-desc">{format.desc}</p>
								</div>
							{/each}
						</div>
					</section>
				</div>

				<!-- Features & Guides Tab -->
			{:else if activeTab === 'features'}
				<div class="help-content">
					<!-- Case Management -->
					<section class="feature-section">
						<div class="feature-header">
							<div class="feature-icon">
								<Briefcase class="h-6 w-6" />
							</div>
							<div>
								<h2 class="feature-heading">Case Management</h2>
								<p class="feature-description">Organize and track your legal document analysis.</p>
							</div>
						</div>
						<div class="feature-details">
							<div class="detail-item">
								<h4 class="detail-title">Creating Cases</h4>
								<p class="detail-text">
									Each case represents a single matter or client. Create a new case from the
									Dashboard or Cases page. You can add a reference number to link it with your
									practice management system.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Case Status Workflow</h4>
								<div class="status-flow">
									<span class="status-badge status-pending">Pending</span>
									<span class="status-arrow">→</span>
									<span class="status-badge status-processing">Processing</span>
									<span class="status-arrow">→</span>
									<span class="status-badge status-completed">Completed</span>
								</div>
								<p class="detail-text-sm">
									Cases progress through these stages as documents are uploaded and analyzed.
								</p>
							</div>
						</div>
					</section>

					<!-- Document Processing -->
					<section class="feature-section">
						<div class="feature-header">
							<div class="feature-icon">
								<FileCheck class="h-6 w-6" />
							</div>
							<div>
								<h2 class="feature-heading">Document Processing</h2>
								<p class="feature-description">How documents are processed and analyzed.</p>
							</div>
						</div>
						<div class="feature-details">
							<div class="detail-item">
								<h4 class="detail-title">Unlimited Document Analysis</h4>
								<p class="detail-text">
									Analyze as many documents as needed—there are no limits on document count per case.
									Upload PDFs, Word documents, images, emails, and more. The system automatically
									extracts text from each format, including OCR for scanned documents and images using GPT-4o Vision.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Batch Uploads</h4>
								<p class="detail-text">
									Drag and drop multiple files at once. Files are processed in parallel for faster
									analysis. Large files (up to 50MB each) are supported.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Document Quality & Verification Hub</h4>
								<p class="detail-text">
									The system indicates document quality after processing. Use the <strong>Verification Hub</strong>
									to manage document issues: view documents by status (Critical, Needs Attention, Ready),
									run bulk OCR on failed extractions, verify document quality, and exclude duplicates.
									The Verification Hub provides triage mode to quickly identify and fix document problems before analysis.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">OCR & Text Extraction</h4>
								<p class="detail-text">
									Scanned PDFs and images are automatically processed using GPT-4o Vision for text extraction.
									If extraction fails or quality is low, you can retry OCR individually or in bulk through
									the Verification Hub. Clear, high-resolution scans (300+ DPI) produce the best OCR results.
								</p>
							</div>
						</div>
					</section>

					<!-- Clio Integration -->
					<section class="feature-section">
						<div class="feature-header">
							<div class="feature-icon">
								<Link2 class="h-6 w-6" />
							</div>
							<div>
								<h2 class="feature-heading">Clio Integration</h2>
								<p class="feature-description">Connect your Clio account to import matters.</p>
							</div>
						</div>
						<div class="feature-details">
							<div class="detail-item">
								<h4 class="detail-title">Connecting to Clio</h4>
								<p class="detail-text">
									Click the <strong>"Clio"</strong> button in the navigation bar to connect your Clio
									account. You'll be redirected to Clio to authorize the connection. A green indicator
									shows when you're connected.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Unlimited Document Import</h4>
								<p class="detail-text">
									Once connected, import complete Clio matters with <strong>no limits on document count</strong>.
									All documents, communications, and notes are imported automatically—no pagination restrictions.
									The improved sync ensures every file is captured accurately.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Synced Content</h4>
								<p class="detail-text">
									The integration imports matter details, all associated documents, email communications,
									and case notes. All imported items are available for analysis with improved reliability
									and performance.
								</p>
							</div>
						</div>
					</section>

					<!-- AI Analysis -->
					<section class="feature-section">
						<div class="feature-header">
							<div class="feature-icon accent">
								<Sparkles class="h-6 w-6" />
							</div>
							<div>
								<h2 class="feature-heading">AI-Powered Analysis</h2>
								<p class="feature-description">How the AI analyzes your documents.</p>
							</div>
						</div>
						<div class="feature-details">
							<div class="detail-item">
								<h4 class="detail-title">Multi-Stage Processing</h4>
								<p class="detail-text">
									Analysis happens in multiple stages: document extraction, fact identification,
									timeline construction, legal issue analysis, gap detection, and comprehensive narrative generation.
									Each stage builds on the previous one for thorough results.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Magazine-Style Full Analysis</h4>
								<p class="detail-text">
									The Full Analysis tab presents your comprehensive case narrative in a beautifully formatted,
									magazine-style editorial layout. Featuring refined typography (Playfair Display + IBM Plex Sans),
									elegant visual hierarchy, and enhanced readability through strategic whitespace and thoughtful styling.
									Transform raw LLM output into a polished, scannable reading experience.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Auto-Fill Legal Issue</h4>
								<p class="detail-text">
									The AI automatically identifies the most likely legal issue based on your intake
									form. You can verify or change the selection before analysis. Choose from 30+
									practice areas including landlord/tenant, contract disputes, personal injury, and
									more.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Verified Legal Corpus (Florida & New Mexico)</h4>
								<p class="detail-text">
									The system validates statute citations against our verified legal corpus. This prevents
									AI hallucination and ensures accurate legal references in your findings emails.
									View the full corpus documentation in the <strong>Legal Knowledge Library</strong> below.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Multi-Model AI Architecture</h4>
								<p class="detail-text">
									Uses specialized AI models for different tasks: GPT-4o for fast document extraction,
									GPT-4o-mini for legal issue identification, GPT-4.1 for comprehensive analysis, and
									GPT-5.2 for professional findings email generation.
								</p>
							</div>
						</div>
					</section>

					<!-- Legal Knowledge Library -->
					<section class="library-section">
						<div class="feature-header">
							<div class="feature-icon library">
								<Library class="h-6 w-6" />
							</div>
							<div>
								<h2 class="feature-heading">Legal Knowledge Library</h2>
								<p class="feature-description">
									Browse the verified legal corpus for Florida and New Mexico. Full documentation, coverage,
									and citation formats are available for each jurisdiction.
								</p>
							</div>
						</div>
						<div class="library-grid">
							<a href="/app/help/corpus/florida" class="library-card florida">
								<div class="library-card-header">
									<div class="library-icon florida">
										<Scale class="h-5 w-5" />
									</div>
									<h3 class="library-title">Florida Legal Corpus</h3>
								</div>
								<p class="library-description">
									51 statutes, 3 rules. Consumer protection, landlord-tenant, construction defects,
									mechanic's liens, foreclosure, insurance, and more.
								</p>
								<div class="library-tags">
									<span class="library-tag florida">FDUTPA</span>
									<span class="library-tag florida">Ch. 83</span>
									<span class="library-tag florida">Ch. 558</span>
									<span class="library-tag florida">Ch. 713</span>
								</div>
								<span class="library-cta">
									Explore Florida statutes
									<ChevronRight class="h-4 w-4" />
								</span>
							</a>
							<a href="/app/help/corpus/new-mexico" class="library-card new-mexico">
								<div class="library-card-header">
									<div class="library-icon new-mexico">
										<Scale class="h-5 w-5" />
									</div>
									<h3 class="library-title">New Mexico Legal Corpus</h3>
								</div>
								<p class="library-description">
									42 statutes, 8 rules. UPA, UORRA, construction & liens, foreclosure,
									insurance & torts, statutes of limitation.
								</p>
								<div class="library-tags">
									<span class="library-tag new-mexico">UPA</span>
									<span class="library-tag new-mexico">UORRA</span>
									<span class="library-tag new-mexico">Civil Proc.</span>
									<span class="library-tag new-mexico">Liens</span>
								</div>
								<span class="library-cta">
									Explore New Mexico statutes
									<ChevronRight class="h-4 w-4" />
								</span>
							</a>
						</div>
					</section>

					<!-- Email Generation -->
					<section class="feature-section">
						<div class="feature-header">
							<div class="feature-icon">
								<Mail class="h-6 w-6" />
							</div>
							<div>
								<h2 class="feature-heading">Letter Generation</h2>
								<p class="feature-description">Create professional findings emails and demand letters.</p>
							</div>
						</div>
						<div class="feature-details">
							<div class="detail-item">
								<h4 class="detail-title">Professional Formatting</h4>
								<p class="detail-text">
									Findings emails and demand letters follow attorney-style formatting with proper structure,
									professional language, and clear organization. All documents are suitable for client
									delivery or internal review.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Citation Management</h4>
								<p class="detail-text">
									All facts in generated letters are cited to source documents. Citations use clean filename
									references so you can verify any statement against the original document.
								</p>
							</div>
							<div class="detail-item">
								<h4 class="detail-title">Review & Edit</h4>
								<p class="detail-text">
									Review all generated content before finalizing. You can edit content, verify facts,
									and adjust language as needed. Export as HTML for further formatting.
								</p>
							</div>
						</div>
					</section>
				</div>

				<!-- FAQ Tab -->
			{:else if activeTab === 'faq'}
				<div class="help-content">
					<div class="faq-intro">
						<div class="flex items-center gap-3">
							<HelpCircle class="h-6 w-6 text-accent" />
							<h2 class="text-xl font-heading font-semibold text-contrast">
								Frequently Asked Questions
							</h2>
						</div>
						<p class="mt-2 text-gray-600">Find answers to common questions about using the portal.</p>
					</div>

					<div class="accordion-container">
						<AccordionItem title="What file formats are supported?">
							<p>
								The portal supports a wide range of document formats including:
							</p>
							<ul class="faq-list">
								<li><strong>PDF</strong> - Standard and scanned (with OCR via GPT-4o Vision)</li>
								<li><strong>DOCX/DOC</strong> - Microsoft Word documents</li>
								<li><strong>TXT</strong> - Plain text files</li>
								<li><strong>CSV</strong> - Spreadsheet data</li>
								<li><strong>JPG/PNG</strong> - Images (text extracted via OCR)</li>
								<li><strong>EML</strong> - Email files</li>
								<li><strong>HTML</strong> - Web page content</li>
							</ul>
							<p class="mt-2">
								Maximum file size is 50MB per file. There is no limit on the number of documents per case.
								For best results, use clear, high-quality scans for OCR processing.
							</p>
						</AccordionItem>

						<AccordionItem title="Is there a limit on the number of documents I can analyze?">
							<p>
								<strong>No!</strong> There are no limits on the number of documents you can upload or analyze per case.
							</p>
							<p class="mt-2">
								Whether you're working with 5 documents or 500, the system will process all of them. This includes
								documents imported from Clio—all pagination limits have been removed, ensuring every document,
								communication, and note is captured.
							</p>
							<div class="mt-3 p-3 bg-green-50 rounded-lg">
								<p class="text-sm text-green-800">
									<strong>Pro Tip:</strong> The system processes documents in parallel, so even large document
									sets are analyzed efficiently. Analysis time scales reasonably with document count.
								</p>
							</div>
						</AccordionItem>

						<AccordionItem title="What jurisdictions are supported?">
							<p>
								The portal is optimized for <strong>Florida and New Mexico</strong> civil litigation:
							</p>
							<ul class="faq-list">
								<li><strong>Florida</strong> - 51 verified statutes covering consumer protection, landlord-tenant,
								construction defects, mechanic's liens, foreclosure, and personal injury</li>
								<li><strong>New Mexico</strong> - 42 verified statutes covering consumer protection (UPA),
								landlord-tenant (UORRA), construction & liens, foreclosure, insurance & torts</li>
							</ul>
							<p class="mt-2">
								You can view the full legal corpus for each jurisdiction from Help:
								<a href="/app/help/corpus/florida" class="text-accent hover:text-accent-hover font-medium">Florida Legal Corpus</a> and
								<a href="/app/help/corpus/new-mexico" class="text-accent hover:text-accent-hover font-medium">New Mexico Legal Corpus</a>.
							</p>
							<p class="mt-2">
								<strong>Not supported:</strong> Federal claims, criminal law, immigration, bankruptcy, or patent/trademark matters.
							</p>
						</AccordionItem>

						<AccordionItem title="How long does analysis take?">
							<p>
								Analysis time depends on the number and complexity of your documents:
							</p>
							<ul class="faq-list">
								<li><strong>Small cases (1-5 documents)</strong> - 1-2 minutes</li>
								<li><strong>Medium cases (5-15 documents)</strong> - 2-4 minutes</li>
								<li><strong>Large cases (15+ documents)</strong> - 4-8 minutes</li>
								<li><strong>Very large cases (50+ documents)</strong> - 10-15 minutes</li>
							</ul>
							<p class="mt-2">
								You'll see real-time progress updates during analysis via Server-Sent Events (SSE) streaming.
								The system processes documents in parallel to minimize wait time.
							</p>
							<div class="mt-2 p-3 bg-amber-50 rounded-lg">
								<p class="text-sm text-amber-800">
									<strong>Note:</strong> If documents need OCR (scanned PDFs or images), add 30-60 seconds per document
									for text extraction using GPT-4o Vision.
								</p>
							</div>
						</AccordionItem>

						<AccordionItem title="What is the Full Analysis tab?">
							<p>
								The <strong>Full Analysis</strong> tab displays your complete case narrative in a beautifully formatted,
								magazine-style editorial layout.
							</p>
							<p class="mt-2">
								Unlike the structured "Case Analysis" tab that organizes information into sections, the Full Analysis
								provides a comprehensive narrative that reads like a professional legal memo. It features:
							</p>
							<ul class="faq-list">
								<li><strong>Refined Typography</strong> - Playfair Display headings with IBM Plex Sans body text</li>
								<li><strong>Visual Hierarchy</strong> - Clear section breaks, pull quotes, and thoughtful spacing</li>
								<li><strong>Enhanced Readability</strong> - Generous whitespace and scannable layout</li>
								<li><strong>Professional Presentation</strong> - Print-friendly and export-ready formatting</li>
							</ul>
							<div class="mt-3 p-3 bg-blue-50 rounded-lg">
								<p class="text-sm text-blue-800">
									<strong>Tip:</strong> The Full Analysis is ideal for comprehensive case review, while the
									structured Case Analysis tab is better for quick reference and fact-checking.
								</p>
							</div>
						</AccordionItem>

						<AccordionItem title="What if my documents fail to process or don't have text?">
							<p class="mb-3">
								The system provides several ways to handle documents that fail to process or don't have extracted text:
							</p>

							<div class="space-y-3">
								<div>
									<h5 class="font-semibold text-contrast text-sm mb-1">Before Analysis</h5>
									<p class="text-sm text-gray-600">
										If you try to start analysis and some documents are missing text, you'll see a warning modal showing which
										documents will be skipped. You have three options:
									</p>
									<ul class="faq-list-sm">
										<li><strong>Run OCR on All</strong> - Automatically extracts text from all documents using GPT-4o Vision (recommended)</li>
										<li><strong>Skip These Documents</strong> - Proceed with analysis excluding those documents</li>
										<li><strong>Cancel</strong> - Go back and fix documents manually</li>
									</ul>
								</div>

								<div>
									<h5 class="font-semibold text-contrast text-sm mb-1">Verification Hub (Document Management)</h5>
									<p class="text-sm text-gray-600">
										Click the <strong>"Verification Hub"</strong> button on your case page to access advanced document management:
									</p>
									<ul class="faq-list-sm">
										<li><strong>Triage Mode</strong> - Documents grouped by status: Critical (failed downloads/corrupted),
										Needs Attention (extraction failed/needs review), Ready, Duplicates, Excluded</li>
										<li><strong>Bulk OCR</strong> - Select multiple documents and run OCR on all at once</li>
										<li><strong>Individual Retry</strong> - Click "Retry" on any failed document to re-run OCR</li>
										<li><strong>Document Preview</strong> - View document content and verify extraction quality</li>
									</ul>
								</div>

								<div>
									<h5 class="font-semibold text-contrast text-sm mb-1">Common Document Issues</h5>
									<div class="text-sm text-gray-600 space-y-1">
										<p><strong>extraction_failed:</strong> Text extraction failed - run OCR to retry</p>
										<p><strong>needs_review:</strong> Low quality extraction - verify or run OCR again</p>
										<p><strong>corrupted:</strong> File is corrupted - re-upload a clean copy</p>
										<p><strong>download_failed:</strong> Upload failed - retry upload</p>
										<p><strong>duplicate:</strong> Same file uploaded twice - can exclude from analysis</p>
									</div>
								</div>
							</div>

							<div class="mt-3 p-3 bg-blue-50 rounded-lg">
								<p class="text-sm text-blue-800">
									<strong>Pro Tip:</strong> OCR works best on clear, high-resolution scans. For poor quality documents,
									consider re-scanning at higher DPI (300+ recommended) before uploading.
								</p>
							</div>
						</AccordionItem>

						<AccordionItem title="Can I edit the generated findings email?">
							<p>
								Yes! The findings email is fully editable. After analysis completes, you can:
							</p>
							<ul class="faq-list">
								<li>Review and modify the content</li>
								<li>Verify facts against source documents</li>
								<li>Adjust language and tone</li>
								<li>Add or remove sections</li>
								<li>Export for further editing in Word or other applications</li>
							</ul>
							<p class="mt-2">
								The findings email is a starting point—always review before sending to clients.
							</p>
						</AccordionItem>

						<AccordionItem title="What is Clio integration?">
							<p>
								Clio is a popular legal practice management software. Our integration allows you to:
							</p>
							<ul class="faq-list">
								<li>Connect your Clio account securely via OAuth</li>
								<li>Search and import matters directly</li>
								<li>Automatically pull <strong>all documents</strong>, communications, and notes (no limits)</li>
								<li>Benefit from improved sync performance and reliability</li>
								<li>Keep your workflow in sync with your existing systems</li>
							</ul>
							<p class="mt-2">
								Click the "Clio" button in the navigation to connect. The integration is optional -
								you can always upload documents manually.
							</p>
							<div class="mt-3 p-3 bg-green-50 rounded-lg">
								<p class="text-sm text-green-800">
									<strong>New:</strong> We've removed all pagination limits! Import complete Clio matters with
									every document, no matter how many files are attached.
								</p>
							</div>
						</AccordionItem>

						<AccordionItem title="How do I connect to Clio?">
							<ol class="faq-list">
								<li>Click the <strong>"Clio"</strong> button in the top navigation bar</li>
								<li>Click <strong>"Connect to Clio"</strong> in the modal that appears</li>
								<li>You'll be redirected to Clio to authorize the connection</li>
								<li>After authorization, you'll return to the portal with a connected status</li>
								<li>A green indicator dot shows when you're successfully connected</li>
							</ol>
							<p class="mt-2">
								Your connection remains active until you disconnect or the authorization expires.
							</p>
						</AccordionItem>

						<AccordionItem title="What if analysis fails?">
							<p>
								If analysis fails, don't worry - your documents are safe. Common causes and solutions:
							</p>
							<ul class="faq-list">
								<li>
									<strong>Poor document quality</strong> - Try uploading clearer scans or the original
									digital files
								</li>
								<li>
									<strong>Corrupted files</strong> - Re-export or re-scan the problematic document
								</li>
								<li>
									<strong>Network issues</strong> - Check your connection and try again
								</li>
								<li>
									<strong>Timeout</strong> - Very large cases may take longer; wait for completion or check system status
								</li>
							</ul>
							<p class="mt-2">
								You can always re-run analysis on a case. Check the document status indicators to
								identify any problematic files.
							</p>
						</AccordionItem>

						<AccordionItem title="How accurate is the AI analysis?">
							<p>
								The AI provides high-quality analysis, but it's a tool to assist - not replace -
								attorney review:
							</p>
							<ul class="faq-list">
								<li>
									<strong>Fact extraction</strong> - Generally very accurate for clear documents
								</li>
								<li>
									<strong>Legal issue identification</strong> - Based on patterns from your intake
									form; verify the selection
								</li>
								<li>
									<strong>Statute citations</strong> - Validated against our Florida & New Mexico Legal Corpus to
									prevent hallucination
								</li>
								<li>
									<strong>Findings email</strong> - Professional quality, but always review before
									sending
								</li>
							</ul>
							<p class="mt-2">
								<strong>Important:</strong> Always verify the generated content against source documents
								before relying on it for legal advice.
							</p>
						</AccordionItem>

						<AccordionItem title="Can I re-run analysis on a case?">
							<p>
								Yes! You can re-run analysis at any time:
							</p>
							<ul class="faq-list">
								<li>Add new documents and run analysis again</li>
								<li>Change the selected legal issue and re-analyze</li>
								<li>Re-run if the initial analysis had issues</li>
							</ul>
							<p class="mt-2">
								Previous analysis results will be replaced with the new analysis. Consider creating a
								new case if you want to preserve old results.
							</p>
						</AccordionItem>

						<AccordionItem title="What practice areas are supported?">
							<p>
								This portal is optimized for <strong>Florida and New Mexico civil litigation matters</strong>. Supported
								areas include:
							</p>
							<div class="practice-areas-grid">
								<div>
									<h5 class="practice-area-heading">Consumer Protection & Business</h5>
									<ul class="practice-area-list">
										<li>Contract disputes</li>
										<li>Consumer protection (FDUTPA/UPA)</li>
										<li>Business organization disputes</li>
									</ul>
								</div>
								<div>
									<h5 class="practice-area-heading">Real Estate & Property</h5>
									<ul class="practice-area-list">
										<li>Landlord-tenant disputes</li>
										<li>Foreclosure defense</li>
										<li>Construction defects</li>
									</ul>
								</div>
								<div>
									<h5 class="practice-area-heading">Civil Litigation</h5>
									<ul class="practice-area-list">
										<li>Statutes of limitation</li>
										<li>Administrative procedure</li>
										<li>Attorney fees matters</li>
									</ul>
								</div>
								<div>
									<h5 class="practice-area-heading">Personal Injury</h5>
									<ul class="practice-area-list">
										<li>Motor vehicle accidents</li>
										<li>Premises liability</li>
										<li>Limited medical malpractice</li>
									</ul>
								</div>
							</div>
							<div class="unsupported-notice">
								<strong>Note:</strong> Federal claims, criminal law, immigration, bankruptcy, and
								patent/trademark matters are not supported.
							</div>
						</AccordionItem>

						<AccordionItem title="How do I contact support?">
							<p>
								If you need help or have questions not covered here:
							</p>
							<ul class="faq-list">
								<li>Check this help documentation first</li>
								<li>Contact your system administrator</li>
								<li>Report technical issues to your IT support team</li>
							</ul>
							<p class="mt-2">
								For feature requests or feedback, please contact your administrator who can relay them
								to the development team.
							</p>
						</AccordionItem>
					</div>
				</div>
			{/if}
		</Tabs>
	</div>

	<!-- Still Need Help Section -->
	<div class="support-card">
		<div class="flex items-start gap-4">
			<div class="support-icon">
				<HelpCircle class="h-6 w-6 text-contrast" />
			</div>
			<div>
				<h3 class="text-lg font-heading font-semibold text-contrast">Still need help?</h3>
				<p class="mt-1 text-gray-600">
					If you couldn't find the answer you're looking for, contact your system administrator or
					IT support team for assistance. You can also browse the
					<a href="/app/help/corpus/florida" class="text-accent hover:text-accent-hover font-medium">Florida</a> and
					<a href="/app/help/corpus/new-mexico" class="text-accent hover:text-accent-hover font-medium">New Mexico</a>
					legal corpus for statute documentation.
				</p>
			</div>
		</div>
	</div>
</div>

<style>
	@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

	/* Container */
	.help-container {
		background: white;
		border-radius: 16px;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
		overflow: hidden;
	}

	.help-content {
		padding: 2.5rem;
	}

	/* Welcome Card */
	.welcome-card {
		background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
		border: 1px solid #e2e8f0;
	}

	.feature-card {
		border-radius: 12px;
		padding: 2rem;
		margin-bottom: 2rem;
	}

	.feature-icon-large {
		flex-shrink: 0;
		width: 56px;
		height: 56px;
		border-radius: 12px;
		background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%);
		color: white;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: 0 4px 12px rgba(var(--accent-rgb), 0.2);
	}

	.feature-heading {
		font-size: 1.5rem;
		font-weight: 700;
		color: var(--contrast);
		margin-bottom: 0.5rem;
		font-family: 'Inter', sans-serif;
	}

	.feature-description {
		font-size: 1rem;
		color: #64748b;
		line-height: 1.6;
	}

	/* Guide Section */
	.guide-section {
		margin: 3rem 0;
	}

	.section-heading {
		font-size: 1.375rem;
		font-weight: 700;
		color: var(--contrast);
		margin-bottom: 1.5rem;
		font-family: 'Inter', sans-serif;
		position: relative;
		padding-bottom: 0.75rem;
	}

	.section-heading::after {
		content: '';
		position: absolute;
		bottom: 0;
		left: 0;
		width: 60px;
		height: 3px;
		background: var(--accent);
		border-radius: 2px;
	}

	.steps-container {
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.step-card {
		display: flex;
		gap: 1.25rem;
		padding: 1.75rem;
		background: white;
		border: 2px solid #f1f5f9;
		border-radius: 12px;
		transition: all 0.2s;
	}

	.step-card:hover {
		border-color: var(--accent);
		box-shadow: 0 4px 12px rgba(var(--accent-rgb), 0.1);
		transform: translateY(-2px);
	}

	.step-number {
		flex-shrink: 0;
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: var(--accent);
		color: white;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 700;
		font-size: 1.125rem;
		box-shadow: 0 2px 8px rgba(var(--accent-rgb), 0.25);
	}

	.step-content {
		flex: 1;
	}

	.step-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.step-title {
		font-weight: 600;
		color: var(--contrast);
		font-size: 1.125rem;
	}

	.step-description {
		color: #64748b;
		font-size: 0.9375rem;
		line-height: 1.7;
	}

	.tip-box {
		margin-top: 1rem;
		padding: 0.875rem 1.125rem;
		background: #dbeafe;
		border-left: 3px solid #3b82f6;
		border-radius: 6px;
	}

	.tip-text {
		font-size: 0.875rem;
		color: #1e40af;
		margin: 0;
	}

	.note-box {
		margin-top: 1rem;
		padding: 0.875rem 1.125rem;
		background: #fef3c7;
		border-left: 3px solid #f59e0b;
		border-radius: 6px;
	}

	.note-text {
		font-size: 0.875rem;
		color: #92400e;
		margin: 0;
	}

	/* Formats Section */
	.formats-section {
		margin: 3rem 0;
		padding-top: 2rem;
		border-top: 1px solid #e2e8f0;
	}

	.formats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
		gap: 1rem;
	}

	.format-card {
		padding: 1.25rem;
		background: #f8fafc;
		border-radius: 10px;
		text-align: center;
		border: 1px solid #e2e8f0;
		transition: all 0.2s;
	}

	.format-card:hover {
		background: white;
		border-color: var(--accent);
		box-shadow: 0 2px 8px rgba(var(--accent-rgb), 0.1);
	}

	.format-ext {
		font-family: 'SF Mono', 'Courier New', monospace;
		font-weight: 700;
		color: var(--contrast);
		font-size: 0.9375rem;
		display: block;
		margin-bottom: 0.5rem;
	}

	.format-desc {
		font-size: 0.75rem;
		color: #64748b;
		margin: 0;
	}

	/* Feature Sections */
	.feature-section {
		margin: 3rem 0;
		padding-top: 2rem;
		border-top: 1px solid #e2e8f0;
	}

	.feature-header {
		display: flex;
		align-items: start;
		gap: 1.25rem;
		margin-bottom: 2rem;
	}

	.feature-icon {
		flex-shrink: 0;
		width: 48px;
		height: 48px;
		border-radius: 10px;
		background: var(--contrast);
		color: white;
		display: flex;
		align-items: center;
		justify-content: center;
		opacity: 0.9;
	}

	.feature-icon.accent {
		background: var(--accent);
		opacity: 1;
	}

	.feature-icon.library {
		background: #1B365D;
		opacity: 1;
	}

	.feature-details {
		margin-left: 4rem;
		display: flex;
		flex-direction: column;
		gap: 1.75rem;
	}

	.detail-item {
		padding-left: 1.5rem;
		border-left: 3px solid #f1f5f9;
	}

	.detail-title {
		font-weight: 600;
		color: var(--contrast);
		margin-bottom: 0.625rem;
		font-size: 1rem;
	}

	.detail-text {
		color: #64748b;
		font-size: 0.9375rem;
		line-height: 1.7;
	}

	.detail-text-sm {
		color: #64748b;
		font-size: 0.875rem;
		line-height: 1.6;
		margin-top: 0.5rem;
	}

	.status-flow {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.status-badge {
		padding: 0.5rem 0.875rem;
		border-radius: 6px;
		font-size: 0.875rem;
		font-weight: 600;
	}

	.status-pending {
		background: #f1f5f9;
		color: #475569;
	}

	.status-processing {
		background: #dbeafe;
		color: #1e40af;
	}

	.status-completed {
		background: #d1fae5;
		color: #065f46;
	}

	.status-arrow {
		color: #cbd5e1;
		font-size: 1.125rem;
	}

	/* Library Section */
	.library-section {
		margin: 3rem 0;
		padding-top: 2.5rem;
		border-top: 2px solid #e2e8f0;
	}

	.library-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 1.5rem;
		margin-top: 1.5rem;
	}

	.library-card {
		display: block;
		padding: 1.75rem;
		border-radius: 14px;
		border: 2px solid;
		transition: all 0.3s;
		text-decoration: none;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
	}

	.library-card.florida {
		border-color: rgba(27, 54, 93, 0.2);
		background: linear-gradient(to bottom right, white, rgba(27, 54, 93, 0.03));
	}

	.library-card.florida:hover {
		border-color: var(--accent);
		box-shadow: 0 8px 24px rgba(var(--accent-rgb), 0.15);
		transform: translateY(-4px);
	}

	.library-card.new-mexico {
		border-color: rgba(45, 125, 125, 0.25);
		background: linear-gradient(to bottom right, white, rgba(45, 125, 125, 0.03));
	}

	.library-card.new-mexico:hover {
		border-color: var(--accent);
		box-shadow: 0 8px 24px rgba(var(--accent-rgb), 0.15);
		transform: translateY(-4px);
	}

	.library-card-header {
		display: flex;
		align-items: center;
		gap: 0.875rem;
		margin-bottom: 1rem;
	}

	.library-icon {
		width: 40px;
		height: 40px;
		border-radius: 8px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: white;
	}

	.library-icon.florida {
		background: #1B365D;
	}

	.library-icon.new-mexico {
		background: #2D7D7D;
	}

	.library-title {
		font-size: 1.125rem;
		font-weight: 700;
		color: var(--contrast);
		margin: 0;
	}

	.library-description {
		font-size: 0.9375rem;
		color: #64748b;
		line-height: 1.6;
		margin-bottom: 1.25rem;
	}

	.library-tags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 1.25rem;
	}

	.library-tag {
		padding: 0.375rem 0.75rem;
		border-radius: 6px;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.library-tag.florida {
		background: rgba(27, 54, 93, 0.1);
		color: #1B365D;
	}

	.library-tag.new-mexico {
		background: rgba(45, 125, 125, 0.15);
		color: #2D7D7D;
	}

	.library-cta {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--accent);
		transition: gap 0.2s;
	}

	/* FAQ */
	.faq-intro {
		margin-bottom: 2rem;
	}

	.accordion-container {
		border-top: 1px solid #e2e8f0;
	}

	.faq-list {
		list-style: disc;
		padding-left: 1.5rem;
		margin: 0.75rem 0;
		color: #64748b;
	}

	.faq-list li {
		margin: 0.5rem 0;
		line-height: 1.6;
	}

	.faq-list-sm {
		list-style: disc;
		padding-left: 1.5rem;
		margin: 0.5rem 0 0 1rem;
		font-size: 0.875rem;
		color: #64748b;
	}

	.faq-list-sm li {
		margin: 0.25rem 0;
	}

	.practice-areas-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 1.5rem;
		margin-top: 1rem;
	}

	.practice-area-heading {
		font-weight: 600;
		font-size: 0.9375rem;
		color: var(--contrast);
		margin-bottom: 0.5rem;
	}

	.practice-area-list {
		list-style: disc;
		padding-left: 1.25rem;
		font-size: 0.875rem;
		color: #64748b;
	}

	.practice-area-list li {
		margin: 0.25rem 0;
	}

	.unsupported-notice {
		margin-top: 1.25rem;
		padding: 0.75rem 1rem;
		background: #fef3c7;
		border-radius: 8px;
		font-size: 0.875rem;
		color: #92400e;
	}

	/* Support Card */
	.support-card {
		margin-top: 2rem;
		padding: 2rem;
		background: #f8fafc;
		border: 1px solid #e2e8f0;
		border-radius: 12px;
	}

	.support-icon {
		padding: 0.75rem;
		background: var(--contrast);
		opacity: 0.1;
		border-radius: 10px;
	}

	/* Responsive */
	@media (max-width: 768px) {
		.help-content {
			padding: 1.5rem;
		}

		.feature-details {
			margin-left: 0;
		}

		.step-card {
			flex-direction: column;
			align-items: start;
		}

		.formats-grid {
			grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		}

		.library-grid {
			grid-template-columns: 1fr;
		}

		.practice-areas-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
