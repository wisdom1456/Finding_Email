<script lang="ts">
  import SlideOutPanel from './ui/SlideOutPanel.svelte';
  import DocumentPreviewPane from './DocumentPreviewPane.svelte';

  let {
    open = false,
    document = null,
    caseId = '',
    onClose,
    onVerify,
    onReExtract,
    onTextEdit
  }: {
    open?: boolean;
    document?: any | null;
    caseId?: string;
    onClose: () => void;
    onVerify: (id: string) => void;
    onReExtract: (id: string) => void;
    onTextEdit: (doc: any) => void;
  } = $props();

  let pdfBlobUrl = $state<string | null>(null);
  let loadingPdf = $state(false);

  function isPdfDocument(doc: any): boolean {
    if (!doc) return false;
    const name = (doc.file_name || '').toLowerCase();
    const type = (doc.file_type || '').toLowerCase();
    return name.endsWith('.pdf') || type.includes('pdf');
  }

  function isImageDocument(doc: any): boolean {
    if (!doc) return false;
    const name = (doc.file_name || '').toLowerCase();
    const type = (doc.file_type || '').toLowerCase();
    const imageExts = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'];
    return imageExts.some(ext => name.endsWith(ext)) || type.startsWith('image/');
  }

  async function loadDocumentBinaryPreview(doc: any) {
    if (!doc?.id) return;
    loadingPdf = true;
    try {
      const response = await fetch(`/api/documents/${doc.id}/download`);
      if (response.ok) {
        const blob = await response.blob();
        pdfBlobUrl = URL.createObjectURL(blob);
      }
    } finally {
      loadingPdf = false;
    }
  }

  // Reset blob URL when document changes
  $effect(() => {
    if (document) {
      pdfBlobUrl = null;
    }
  });
</script>

<SlideOutPanel {open} title={document?.file_name ?? ''} width="82%" {onClose}>
  {#snippet children()}
    <div class="flex h-full overflow-hidden">
      <!-- Left: PDF Preview -->
      <div class="w-1/2 border-r border-gray-200 overflow-hidden flex flex-col">
        <div class="px-3 py-2 bg-gray-50 border-b border-gray-100 flex items-center gap-2 flex-shrink-0">
          <span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Original Document</span>
        </div>
        <div class="flex-1 overflow-hidden">
          {#if document}
            <DocumentPreviewPane
              fileName={document.file_name}
              fileType={document.file_type}
              documentId={document.id}
              hasStoragePath={Boolean(document.storage_path)}
              previewUrl={pdfBlobUrl}
              loading={loadingPdf}
              isPdf={isPdfDocument(document)}
              isImage={isImageDocument(document)}
              isTextDocument={false}
              textPreview=""
              onLoadPreview={() => loadDocumentBinaryPreview(document)}
              loadingLabel="Loading preview..."
              pdfHintMessage="Load inline preview only when needed to keep the viewer responsive."
              unavailableStorageMessage="The original file could not be loaded from storage."
              loadPdfLabel="Load PDF Preview"
              loadImageLabel="Load Image Preview"
              openLinkLabel="Open in New Tab"
              openInNewTab={true}
              linkDownload={false}
              noPreviewTitle={document.extracted_text ? 'No File Preview' : 'Preview Unavailable'}
              noPreviewDescription={document.extracted_text
                ? 'View the extracted text on the right.'
                : "This document doesn't have a preview available."}
              previewHeightClass="h-full"
              wrapperClass="h-full"
            />
          {/if}
        </div>
      </div>

      <!-- Right: Extracted Text -->
      <div class="w-1/2 flex flex-col overflow-hidden">
        <div class="px-3 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between flex-shrink-0">
          <span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Extracted Text</span>
          {#if document?.metadata?.manual_text}
            <span class="text-xs bg-amber-100 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-semibold">
              Manually Edited
            </span>
          {/if}
        </div>
        <div class="flex-1 overflow-y-auto p-4">
          <pre class="text-xs text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">{document?.metadata?.manual_text || document?.extracted_text || '(No text extracted)'}</pre>
        </div>
      </div>
    </div>
  {/snippet}

  {#snippet footer()}
    <div class="p-3 flex items-center gap-2 border-t border-gray-100">
      <button class="btn btn-secondary btn-sm" onclick={() => document && onReExtract(document.id)}>
        Re-extract OCR
      </button>
      <button class="btn btn-secondary btn-sm" onclick={() => document && onTextEdit(document)}>
        Edit Text
      </button>
      <div class="flex-1"></div>
      <button class="btn btn-primary btn-sm" onclick={() => document && onVerify(document.id)}>
        ✓ Verify
      </button>
    </div>
  {/snippet}
</SlideOutPanel>
