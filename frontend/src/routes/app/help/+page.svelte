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
		Scale
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
									letters using AI-powered analysis.
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
										facts, analyzing legal issues, and generating a comprehensive findings letter.
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
										When analysis is complete, review the generated findings letter, document
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
										<h4 class="font-semibold text-contrast">Generate & Export Letter</h4>
									</div>
									<p class="text-gray-600 text-sm">
										Generate your final findings letter with professional formatting. The letter
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
									extracts text from each format, including OCR for scanned documents and images.
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
								<h4 class="font-semibold text-contrast mb-2">Document Quality</h4>
								<p class="text-gray-600 text-sm">
									The system indicates document quality after processing. Low-quality scans or
									corrupted files will be flagged so you can provide better source documents.
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
									timeline construction, legal issue analysis, and findings letter generation. Each
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
								<h4 class="font-semibold text-contrast mb-2">Florida Legal Corpus</h4>
								<p class="text-gray-600 text-sm">
									The system validates statute citations against 51+ verified Florida statutes. This
									prevents AI hallucination and ensures accurate legal references in your findings
									letters.
								</p>
							</div>
						</div>
					</section>

					<!-- Letter Generation -->
					<section class="border-t border-gray-200 pt-6">
						<div class="flex items-start gap-4 mb-4">
							<div class="p-3 bg-contrast/10 rounded-lg">
								<Mail class="h-6 w-6 text-contrast" />
							</div>
							<div>
								<h2 class="text-xl font-heading font-semibold text-contrast">Letter Generation</h2>
								<p class="mt-1 text-gray-600">Create professional findings letters.</p>
							</div>
						</div>
						<div class="ml-16 space-y-4">
							<div>
								<h4 class="font-semibold text-contrast mb-2">Professional Formatting</h4>
								<p class="text-gray-600 text-sm">
									Generated letters follow attorney-style formatting with proper structure,
									professional language, and clear organization. Letters are suitable for client
									delivery or internal review.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Citation Management</h4>
								<p class="text-gray-600 text-sm">
									All facts in the letter are cited to source documents. Citations use clean filename
									references so you can verify any statement against the original document.
								</p>
							</div>
							<div>
								<h4 class="font-semibold text-contrast mb-2">Review & Edit</h4>
								<p class="text-gray-600 text-sm">
									Review the generated letter before finalizing. You can edit content, verify facts,
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
								<li><strong>PDF</strong> - Standard and scanned (with OCR)</li>
								<li><strong>DOCX/DOC</strong> - Microsoft Word documents</li>
								<li><strong>TXT</strong> - Plain text files</li>
								<li><strong>CSV</strong> - Spreadsheet data</li>
								<li><strong>JPG/PNG</strong> - Images (text extracted via OCR)</li>
								<li><strong>EML</strong> - Email files</li>
								<li><strong>HTML</strong> - Web page content</li>
							</ul>
							<p class="mt-2">
								Maximum file size is 50MB per file. For best results, use clear, high-quality scans.
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
								You'll see real-time progress updates during analysis. The system processes documents
								in parallel to minimize wait time.
							</p>
						</AccordionItem>

						<AccordionItem title="Can I edit the generated letter?">
							<p>
								Yes! The findings letter is fully editable. After analysis completes, you can:
							</p>
							<ul class="list-disc list-inside mt-2 space-y-1">
								<li>Review and modify the content</li>
								<li>Verify facts against source documents</li>
								<li>Adjust language and tone</li>
								<li>Add or remove sections</li>
								<li>Export for further editing in Word or other applications</li>
							</ul>
							<p class="mt-2">
								The generated letter is a starting point - always review before sending to clients.
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
									<strong>Findings letter</strong> - Professional quality, but always review before
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
					IT support team for assistance.
				</p>
			</div>
		</div>
	</div>
</div>
