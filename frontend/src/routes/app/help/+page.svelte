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
		Library
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

	<div class="card-standard">
		<Tabs {tabs} bind:activeTab>
			<!-- Getting Started Tab -->
			{#if activeTab === 'getting-started'}
				<div class="space-y-8">
					<!-- Welcome Section -->
					<section>
						<div class="flex items-start gap-4 mb-4">
							<div class="p-3 bg-accent/10 rounded-lg">
								<BookOpen class="h-6 w-6 text-accent" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">
									Welcome to the Legal Document Analysis Portal
								</h2>
								<p class="mt-1 text-gray-600">
									This portal helps you analyze legal documents and generate professional findings
									emails using AI-powered analysis.
								</p>
							</div>
						</div>
					</section>

					<!-- Step by Step Guide -->
					<section>
						<h3 class="text-lg font-heading font-semibold text-contrast mb-4">
							Quick Start Guide
						</h3>
						<div class="space-y-6">
							<!-- Step 1 -->
							<div class="flex gap-4">
								<div
									class="shrink-0 w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center font-semibold text-sm"
								>
									1
								</div>
								<div class="flex-1">
									<div class="flex items-center gap-2 mb-2">
										<FolderOpen class="h-5 w-5 text-contrast-light" />
										<h4 class="font-semibold text-contrast">Create a New Case</h4>
									</div>
									<p class="text-gray-600 text-sm">
										Click the <strong>"New Case"</strong> button on the Dashboard or Cases page. Enter
										your client's name and an optional reference number (like a matter ID from your practice
										management system).
									</p>
								</div>
							</div>

							<!-- Step 2 -->
							<div class="flex gap-4">
								<div
									class="shrink-0 w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center font-semibold text-sm"
								>
									2
								</div>
								<div class="flex-1">
									<div class="flex items-center gap-2 mb-2">
										<Upload class="h-5 w-5 text-contrast-light" />
										<h4 class="font-semibold text-contrast">Upload Documents</h4>
									</div>
									<p class="text-gray-600 text-sm">
										Upload your case documents including intake forms, contracts, correspondence, and
										supporting evidence. You can drag and drop multiple files at once. Supported
										formats include PDF, DOCX, DOC, images (JPG, PNG), TXT, CSV, and EML files.
									</p>
									<div class="mt-2 p-3 bg-blue-50 rounded-lg">
										<p class="text-sm text-blue-800">
											<strong>Tip:</strong> Include your client intake form for best results. The AI
											uses this to understand the case context.
										</p>
									</div>
								</div>
							</div>

							<!-- Step 3 -->
							<div class="flex gap-4">
								<div
									class="shrink-0 w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center font-semibold text-sm"
								>
									3
								</div>
								<div class="flex-1">
									<div class="flex items-center gap-2 mb-2">
										<Play class="h-5 w-5 text-contrast-light" />
										<h4 class="font-semibold text-contrast">Start Analysis</h4>
									</div>
									<p class="text-gray-600 text-sm">
										Once your documents are uploaded, click <strong>"Start Analysis"</strong>. The AI
										will process your documents in multiple stages: extracting text, identifying key
										facts, analyzing legal issues, and generating a comprehensive findings email.
									</p>
									<div class="mt-2 p-3 bg-amber-50 rounded-lg">
										<p class="text-sm text-amber-800">
											<strong>Note:</strong> Analysis typically takes 2-5 minutes depending on the number
											and complexity of documents.
										</p>
									</div>
								</div>
							</div>

							<!-- Step 4 -->
							<div class="flex gap-4">
								<div
									class="shrink-0 w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center font-semibold text-sm"
								>
									4
								</div>
								<div class="flex-1">
									<div class="flex items-center gap-2 mb-2">
										<FileText class="h-5 w-5 text-contrast-light" />
										<h4 class="font-semibold text-contrast">Review Results</h4>
									</div>
									<p class="text-gray-600 text-sm">
										When analysis is complete, review the generated findings email, document
										summaries, and case analysis. You can verify extracted facts, check citations,
										and make edits before finalizing.
									</p>
								</div>
							</div>

							<!-- Step 5 -->
							<div class="flex gap-4">
								<div
									class="shrink-0 w-8 h-8 rounded-full bg-accent text-white flex items-center justify-center font-semibold text-sm"
								>
									5
								</div>
								<div class="flex-1">
									<div class="flex items-center gap-2 mb-2">
										<Mail class="h-5 w-5 text-contrast-light" />
										<h4 class="font-semibold text-contrast">Generate & Export Email</h4>
									</div>
									<p class="text-gray-600 text-sm">
										Generate your final findings email with professional formatting. The email
										includes proper citations to source documents and is ready for client delivery or
										further editing.
									</p>
								</div>
							</div>
						</div>
					</section>

					<!-- Supported Document Formats -->
					<section class="border-t border-gray-200 pt-6">
						<h3 class="text-lg font-heading font-semibold text-contrast mb-4">
							Supported Document Formats
						</h3>
						<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
							{#each [{ ext: 'PDF', desc: 'Adobe PDF' }, { ext: 'DOCX', desc: 'Word Document' }, { ext: 'DOC', desc: 'Word (Legacy)' }, { ext: 'TXT', desc: 'Plain Text' }, { ext: 'CSV', desc: 'Spreadsheets' }, { ext: 'JPG/PNG', desc: 'Images (OCR)' }, { ext: 'EML', desc: 'Email Files' }, { ext: 'HTML', desc: 'Web Pages' }] as format}
								<div class="p-3 bg-gray-50 rounded-lg text-center">
									<span class="font-mono font-semibold text-contrast text-sm">{format.ext}</span>
									<p class="text-xs text-gray-500 mt-1">{format.desc}</p>
								</div>
							{/each}
						</div>
					</section>
				</div>

				<!-- Features & Guides Tab -->
			{:else if activeTab === 'features'}
				<div class="space-y-8">
					<!-- Case Management -->
					<section>
						<div class="flex items-start gap-4 mb-4">
							<div class="p-3 bg-contrast/10 rounded-lg">
								<Briefcase class="h-6 w-6 text-contrast" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">Case Management</h2>
								<p class="mt-1 text-gray-600">Organize and track your legal document analysis.</p>
							</div>
						</div>
						<div class="ml-16 space-y-4">
							<div>
								<h4 class="font-semibold text-contrast mb-2">Creating Cases</h4>
								<p class="text-gray-600 text-sm">
									Each case represents a single matter or client. Create a new case from the
									Dashboard or Cases page. You can add a reference number to link it with your
									practice management system.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Case Status Workflow</h4>
								<div class="flex flex-wrap items-center gap-2 text-sm">
									<span class="px-2 py-1 bg-gray-100 rounded text-gray-700">Pending</span>
									<span class="text-gray-400">→</span>
									<span class="px-2 py-1 bg-blue-100 rounded text-blue-700">Processing</span>
									<span class="text-gray-400">→</span>
									<span class="px-2 py-1 bg-green-100 rounded text-green-700">Completed</span>
								</div>
								<p class="text-gray-500 text-sm mt-2">
									Cases progress through these stages as documents are uploaded and analyzed.
								</p>
							</div>
						</div>
					</section>

					<!-- Document Processing -->
					<section class="border-t border-gray-200 pt-6">
						<div class="flex items-start gap-4 mb-4">
							<div class="p-3 bg-contrast/10 rounded-lg">
								<FileCheck class="h-6 w-6 text-contrast" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">Document Processing</h2>
								<p class="mt-1 text-gray-600">How documents are processed and analyzed.</p>
							</div>
						</div>
						<div class="ml-16 space-y-4">
							<div>
								<h4 class="font-semibold text-contrast mb-2">Multi-Format Support</h4>
								<p class="text-gray-600 text-sm">
									Upload PDFs, Word documents, images, emails, and more. The system automatically
									extracts text from each format, including OCR for scanned documents and images using GPT-4o Vision.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Batch Uploads</h4>
								<p class="text-gray-600 text-sm">
									Drag and drop multiple files at once. Files are processed in parallel for faster
									analysis. Large files (up to 50MB each) are supported.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Document Quality & Verification Hub</h4>
								<p class="text-gray-600 text-sm">
									The system indicates document quality after processing. Use the <strong>Verification Hub</strong> 
									to manage document issues: view documents by status (Critical, Needs Attention, Ready), 
									run bulk OCR on failed extractions, verify document quality, and exclude duplicates. 
									The Verification Hub provides triage mode to quickly identify and fix document problems before analysis.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">OCR & Text Extraction</h4>
								<p class="text-gray-600 text-sm">
									Scanned PDFs and images are automatically processed using GPT-4o Vision for text extraction. 
									If extraction fails or quality is low, you can retry OCR individually or in bulk through 
									the Verification Hub. Clear, high-resolution scans (300+ DPI) produce the best OCR results.
								</p>
							</div>
						</div>
					</section>

					<!-- Clio Integration -->
					<section class="border-t border-gray-200 pt-6">
						<div class="flex items-start gap-4 mb-4">
							<div class="p-3 bg-contrast/10 rounded-lg">
								<Link2 class="h-6 w-6 text-contrast" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">Clio Integration</h2>
								<p class="mt-1 text-gray-600">Connect your Clio account to import matters.</p>
							</div>
						</div>
						<div class="ml-16 space-y-4">
							<div>
								<h4 class="font-semibold text-contrast mb-2">Connecting to Clio</h4>
								<p class="text-gray-600 text-sm">
									Click the <strong>"Clio"</strong> button in the navigation bar to connect your Clio
									account. You'll be redirected to Clio to authorize the connection. A green indicator
									shows when you're connected.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Importing Matters</h4>
								<p class="text-gray-600 text-sm">
									Once connected, you can search for matters by client name or matter number. Select a
									matter to import its details, documents, and communications automatically.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Synced Content</h4>
								<p class="text-gray-600 text-sm">
									The integration imports matter details, associated documents, email communications,
									and notes. All imported items are available for analysis.
								</p>
							</div>
						</div>
					</section>

					<!-- AI Analysis -->
					<section class="border-t border-gray-200 pt-6">
						<div class="flex items-start gap-4 mb-4">
							<div class="p-3 bg-accent/10 rounded-lg">
								<Sparkles class="h-6 w-6 text-accent" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">AI-Powered Analysis</h2>
								<p class="mt-1 text-gray-600">How the AI analyzes your documents.</p>
							</div>
						</div>
						<div class="ml-16 space-y-4">
							<div>
								<h4 class="font-semibold text-contrast mb-2">Multi-Stage Processing</h4>
								<p class="text-gray-600 text-sm">
									Analysis happens in multiple stages: document extraction, fact identification,
									timeline construction, legal issue analysis, and findings email generation. Each
									stage builds on the previous one for comprehensive results.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Auto-Fill Legal Issue</h4>
								<p class="text-gray-600 text-sm">
									The AI automatically identifies the most likely legal issue based on your intake
									form. You can verify or change the selection before analysis. Choose from 30+
									practice areas including landlord/tenant, contract disputes, personal injury, and
									more.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Verified Legal Corpus (Florida & New Mexico)</h4>
								<p class="text-gray-600 text-sm">
									The system validates statute citations against our verified legal corpus. This prevents 
									AI hallucination and ensures accurate legal references in your findings emails. 
									View the full corpus documentation in the <strong>Legal Knowledge Library</strong> below.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Multi-Model AI Architecture</h4>
								<p class="text-gray-600 text-sm">
									Uses specialized AI models for different tasks: GPT-4o for fast document extraction, 
									GPT-4o-mini for legal issue identification, GPT-4.1 for comprehensive analysis, and 
									GPT-5.2 for professional findings email generation.
								</p>
							</div>
						</div>
					</section>

					<!-- Legal Knowledge Library -->
					<section class="border-t border-gray-200 pt-8">
						<div class="flex items-start gap-4 mb-6">
							<div class="p-3 rounded-xl bg-[#1B365D]/10 border border-[#1B365D]/20">
								<Library class="h-6 w-6 text-[#1B365D]" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">Legal Knowledge Library</h2>
								<p class="mt-1 text-gray-600">
									Browse the verified legal corpus for Florida and New Mexico. Full documentation, coverage, 
									and citation formats are available for each jurisdiction.
								</p>
							</div>
						</div>
						<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
							<a
								href="/app/help/corpus/florida"
								class="group block rounded-xl border-2 border-[#1B365D]/20 bg-linear-to-br from-white to-[#1B365D]/5 p-6 shadow-sm transition-all hover:border-accent/40 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
							>
								<div class="flex items-center gap-3 mb-3">
									<div class="flex h-10 w-10 items-center justify-center rounded-lg bg-[#1B365D] text-white">
										<Scale class="h-5 w-5" />
									</div>
									<h3 class="text-lg font-heading font-semibold text-contrast">Florida Legal Corpus</h3>
								</div>
								<p class="text-sm text-gray-600 mb-4">
									51 statutes, 3 rules. Consumer protection, landlord-tenant, construction defects, 
									mechanic's liens, foreclosure, insurance, and more.
								</p>
								<div class="flex flex-wrap gap-2 mb-4">
									<span class="inline-flex items-center rounded-md bg-[#1B365D]/10 px-2.5 py-0.5 text-xs font-medium text-[#1B365D]">FDUTPA</span>
									<span class="inline-flex items-center rounded-md bg-[#1B365D]/10 px-2.5 py-0.5 text-xs font-medium text-[#1B365D]">Ch. 83</span>
									<span class="inline-flex items-center rounded-md bg-[#1B365D]/10 px-2.5 py-0.5 text-xs font-medium text-[#1B365D]">Ch. 558</span>
									<span class="inline-flex items-center rounded-md bg-[#1B365D]/10 px-2.5 py-0.5 text-xs font-medium text-[#1B365D]">Ch. 713</span>
								</div>
								<span class="inline-flex items-center gap-1 text-sm font-semibold text-accent group-hover:gap-2 transition-all">
									Explore Florida statutes
									<ChevronRight class="h-4 w-4" />
								</span>
							</a>
							<a
								href="/app/help/corpus/new-mexico"
								class="group block rounded-xl border-2 border-[#2D7D7D]/25 bg-linear-to-br from-white to-[#2D7D7D]/5 p-6 shadow-sm transition-all hover:border-accent/40 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
							>
								<div class="flex items-center gap-3 mb-3">
									<div class="flex h-10 w-10 items-center justify-center rounded-lg bg-[#2D7D7D] text-white">
										<Scale class="h-5 w-5" />
									</div>
									<h3 class="text-lg font-heading font-semibold text-contrast">New Mexico Legal Corpus</h3>
								</div>
								<p class="text-sm text-gray-600 mb-4">
									42 statutes, 8 rules. UPA, UORRA, construction & liens, foreclosure, 
									insurance & torts, statutes of limitation.
								</p>
								<div class="flex flex-wrap gap-2 mb-4">
									<span class="inline-flex items-center rounded-md bg-[#2D7D7D]/15 px-2.5 py-0.5 text-xs font-medium text-[#2D7D7D]">UPA</span>
									<span class="inline-flex items-center rounded-md bg-[#2D7D7D]/15 px-2.5 py-0.5 text-xs font-medium text-[#2D7D7D]">UORRA</span>
									<span class="inline-flex items-center rounded-md bg-[#2D7D7D]/15 px-2.5 py-0.5 text-xs font-medium text-[#2D7D7D]">Civil Proc.</span>
									<span class="inline-flex items-center rounded-md bg-[#2D7D7D]/15 px-2.5 py-0.5 text-xs font-medium text-[#2D7D7D]">Liens</span>
								</div>
								<span class="inline-flex items-center gap-1 text-sm font-semibold text-accent group-hover:gap-2 transition-all">
									Explore New Mexico statutes
									<ChevronRight class="h-4 w-4" />
								</span>
							</a>
						</div>
					</section>

					<!-- Email Generation (Findings Email) -->
					<section class="border-t border-gray-200 pt-6">
						<div class="flex items-start gap-4 mb-4">
							<div class="p-3 bg-contrast/10 rounded-lg">
								<Mail class="h-6 w-6 text-contrast" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">Email Generation</h2>
								<p class="mt-1 text-gray-600">Create professional findings emails.</p>
							</div>
						</div>
						<div class="ml-16 space-y-4">
							<div>
								<h4 class="font-semibold text-contrast mb-2">Professional Formatting</h4>
								<p class="text-gray-600 text-sm">
									Findings emails follow attorney-style formatting with proper structure,
									professional language, and clear organization. Emails are suitable for client
									delivery or internal review.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Citation Management</h4>
								<p class="text-gray-600 text-sm">
									All facts in the findings email are cited to source documents. Citations use clean filename
									references so you can verify any statement against the original document.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Review & Edit</h4>
								<p class="text-gray-600 text-sm">
									Review the findings email before finalizing. You can edit content, verify facts,
									and adjust language as needed. Export as HTML for further formatting.
								</p>
							</div>
						</div>
					</section>
				</div>

				<!-- FAQ Tab -->
			{:else if activeTab === 'faq'}
				<div class="space-y-2">
					<div class="mb-6">
						<div class="flex items-center gap-3">
							<HelpCircle class="h-6 w-6 text-accent" />
							<h2 class="text-xl font-heading font-semibold text-contrast">
								Frequently Asked Questions
							</h2>
						</div>
						<p class="mt-2 text-gray-600">Find answers to common questions about using the portal.</p>
					</div>

					<div class="divide-y divide-gray-200 border-t border-gray-200">
						<AccordionItem title="What file formats are supported?">
							<p>
								The portal supports a wide range of document formats including:
							</p>
							<ul class="list-disc list-inside mt-2 space-y-1">
								<li><strong>PDF</strong> - Standard and scanned (with OCR via GPT-4o Vision)</li>
								<li><strong>DOCX/DOC</strong> - Microsoft Word documents</li>
								<li><strong>TXT</strong> - Plain text files</li>
								<li><strong>CSV</strong> - Spreadsheet data</li>
								<li><strong>JPG/PNG</strong> - Images (text extracted via OCR)</li>
								<li><strong>EML</strong> - Email files</li>
								<li><strong>HTML</strong> - Web page content</li>
							</ul>
							<p class="mt-2">
								Maximum file size is 50MB per file. For best results, use clear, high-quality scans for OCR processing.
							</p>
						</AccordionItem>

						<AccordionItem title="What jurisdictions are supported?">
							<p>
								The portal is optimized for <strong>Florida and New Mexico</strong> civil litigation:
							</p>
							<ul class="list-disc list-inside mt-2 space-y-1">
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
							<ul class="list-disc list-inside mt-2 space-y-1">
								<li><strong>Small cases (1-5 documents)</strong> - 1-2 minutes</li>
								<li><strong>Medium cases (5-15 documents)</strong> - 2-4 minutes</li>
								<li><strong>Large cases (15+ documents)</strong> - 4-8 minutes</li>
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
									<ul class="list-disc list-inside mt-1 text-sm text-gray-600 ml-4">
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
									<ul class="list-disc list-inside mt-1 text-sm text-gray-600 ml-4">
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
							<ul class="list-disc list-inside mt-2 space-y-1">
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
							<ul class="list-disc list-inside mt-2 space-y-1">
								<li>Connect your Clio account securely via OAuth</li>
								<li>Search and import matters directly</li>
								<li>Automatically pull documents, communications, and notes</li>
								<li>Keep your workflow in sync with your existing systems</li>
							</ul>
							<p class="mt-2">
								Click the "Clio" button in the navigation to connect. The integration is optional -
								you can always upload documents manually.
							</p>
						</AccordionItem>

						<AccordionItem title="How do I connect to Clio?">
							<ol class="list-decimal list-inside mt-2 space-y-2">
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
							<ul class="list-disc list-inside mt-2 space-y-1">
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
									<strong>Timeout</strong> - Very large cases may need to be split into smaller batches
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
							<ul class="list-disc list-inside mt-2 space-y-1">
								<li>
									<strong>Fact extraction</strong> - Generally very accurate for clear documents
								</li>
								<li>
									<strong>Legal issue identification</strong> - Based on patterns from your intake
									form; verify the selection
								</li>
								<li>
									<strong>Statute citations</strong> - Validated against our Florida Legal Corpus to
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
							<ul class="list-disc list-inside mt-2 space-y-1">
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
								This portal is optimized for <strong>Florida civil litigation matters</strong>. Supported
								areas include:
							</p>
							<div class="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-4">
								<div>
									<h5 class="font-semibold text-sm">Consumer Protection & Business</h5>
									<ul class="list-disc list-inside text-sm mt-1">
										<li>Contract disputes</li>
										<li>Consumer protection (FDUTPA)</li>
										<li>Business organization disputes</li>
									</ul>
								</div>
								<div>
									<h5 class="font-semibold text-sm">Real Estate & Property</h5>
									<ul class="list-disc list-inside text-sm mt-1">
										<li>Landlord-tenant disputes</li>
										<li>Foreclosure defense</li>
										<li>Construction defects</li>
									</ul>
								</div>
								<div>
									<h5 class="font-semibold text-sm">Civil Litigation</h5>
									<ul class="list-disc list-inside text-sm mt-1">
										<li>Statutes of limitation</li>
										<li>Administrative procedure</li>
										<li>Attorney fees matters</li>
									</ul>
								</div>
								<div>
									<h5 class="font-semibold text-sm">Personal Injury</h5>
									<ul class="list-disc list-inside text-sm mt-1">
										<li>Motor vehicle accidents</li>
										<li>Premises liability</li>
										<li>Limited medical malpractice</li>
									</ul>
								</div>
							</div>
							<p class="mt-3 text-sm text-amber-700 bg-amber-50 p-2 rounded">
								<strong>Note:</strong> Federal claims, criminal law, immigration, bankruptcy, and
								patent/trademark matters are not supported.
							</p>
						</AccordionItem>

						<AccordionItem title="How do I contact support?">
							<p>
								If you need help or have questions not covered here:
							</p>
							<ul class="list-disc list-inside mt-2 space-y-1">
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
	<div class="mt-8 card-standard bg-gray-50 border border-gray-200">
		<div class="flex items-start gap-4">
			<div class="p-3 bg-contrast/10 rounded-lg">
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
