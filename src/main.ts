// Configuration
const WEBHOOK_URL = 'https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload';
const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB in bytes

// Type definitions
interface FileData {
  file: File;
  name: string;
  size: number;
  type: string;
}

interface AnalysisResult {
  status: string;
  message?: string;
  documentsProcessed?: number;
  downloadLinks?: {
    findingsLetter?: string;
    caseAnalysis?: string;
    executiveSummary?: string;
  };
}

// Global variables
let intakeForm: FileData | null = null;
let caseDocuments = new Map<string, FileData>();
let fileCounter = 0;

// DOM elements
let intakeUploadSection: HTMLElement;
let documentsUploadSection: HTMLElement;
let intakeInput: HTMLInputElement;
let documentsInput: HTMLInputElement;
let intakeStatus: HTMLElement;
let fileManager: HTMLElement;
let fileListContainer: HTMLElement;
let submitBtn: HTMLButtonElement;
let statusElement: HTMLElement;
let sizeWarning: HTMLElement;

// Utility functions
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Event handlers for drag and drop
function handleDragOver(e: DragEvent, isIntake: boolean): void {
  e.preventDefault();
  if (isIntake) {
    intakeUploadSection.classList.add('dragover');
  } else {
    documentsUploadSection.classList.add('dragover');
  }
}

function handleDragLeave(e: DragEvent, isIntake: boolean): void {
  e.preventDefault();
  if (isIntake) {
    intakeUploadSection.classList.remove('dragover');
  } else {
    documentsUploadSection.classList.remove('dragover');
  }
}

function handleDrop(e: DragEvent, isIntake: boolean): void {
  e.preventDefault();
  if (isIntake) {
    intakeUploadSection.classList.remove('dragover');
  } else {
    documentsUploadSection.classList.remove('dragover');
  }
  
  const files = Array.from(e.dataTransfer?.files || []);
  processFiles(files, isIntake);
}

function handleFileSelect(e: Event, isIntake: boolean): void {
  const target = e.target as HTMLInputElement;
  const files = Array.from(target.files || []);
  processFiles(files, isIntake);
  
  // Reset the input
  target.value = '';
}

// File processing
function processFiles(files: File[], isIntake: boolean): void {
  const supportedTypes = ['pdf', 'docx', 'doc', 'txt'];
  
  if (isIntake) {
    // Only allow one intake form
    if (files.length > 1) {
      showIntakeStatus('⚠️ Please select only one intake form file.', 'error');
      return;
    }
    
    const file = files[0];
    if (!file) return;
    
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!extension || !['pdf', 'docx', 'doc'].includes(extension)) {
      showIntakeStatus('⚠️ Please select a PDF or Word document for the intake form.', 'error');
      return;
    }
    
    intakeForm = {
      file: file,
      name: file.name,
      size: file.size,
      type: extension
    };
    
    showIntakeStatus(`✅ Intake form uploaded: ${file.name}`, 'success');
  } else {
    // Process case documents
    files.forEach(file => {
      const extension = file.name.split('.').pop()?.toLowerCase();
      
      if (extension && supportedTypes.includes(extension)) {
        const fileId = 'file_' + (++fileCounter);
        
        caseDocuments.set(fileId, {
          file: file,
          name: file.name,
          size: file.size,
          type: extension
        });
      } else {
        console.warn(`Skipped unsupported file: ${file.name}`);
      }
    });
  }
  
  updateFileDisplay();
  updateSubmitButton();
}

function showIntakeStatus(message: string, type: string): void {
  intakeStatus.textContent = message;
  intakeStatus.className = `requirement-note ${type}`;
  intakeStatus.style.display = 'block';
}

function updateFileDisplay(): void {
  const hasFiles = intakeForm || caseDocuments.size > 0;
  
  if (!hasFiles) {
    fileManager.style.display = 'none';
    return;
  }
  
  fileManager.style.display = 'block';
  
  // Update statistics
  const totalSize = (intakeForm ? intakeForm.size : 0) + 
                   Array.from(caseDocuments.values()).reduce((sum, file) => sum + file.size, 0);
  
  (document.getElementById('intakeCount') as HTMLElement).textContent = intakeForm ? '1' : '0';
  (document.getElementById('totalFiles') as HTMLElement).textContent = caseDocuments.size.toString();
  (document.getElementById('totalSize') as HTMLElement).textContent = formatFileSize(totalSize);
  
  // Show size warning
  if (totalSize > MAX_FILE_SIZE * 0.8) {
    sizeWarning.style.display = 'block';
    if (totalSize > MAX_FILE_SIZE) {
      sizeWarning.textContent = '❌ Total file size exceeds 100MB limit. Please remove some files.';
      sizeWarning.classList.add('size-error');
    } else {
      sizeWarning.textContent = '⚠️ Total file size is approaching the 100MB limit';
      sizeWarning.classList.remove('size-error');
    }
  } else {
    sizeWarning.style.display = 'none';
  }
  
  // Update file list
  fileListContainer.innerHTML = '';
  
  // Add intake form if present
  if (intakeForm) {
    const fileItem = document.createElement('div');
    fileItem.className = 'file-item intake-file';
    fileItem.innerHTML = `
      <div class="file-name">${intakeForm.name}</div>
      <div class="file-type intake">${intakeForm.type.toUpperCase()}</div>
      <div class="file-category category-intake">INTAKE FORM</div>
      <div class="file-size">${formatFileSize(intakeForm.size)}</div>
      <button type="button" class="file-remove" onclick="removeIntakeForm()">
        Remove
      </button>
    `;
    fileListContainer.appendChild(fileItem);
  }
  
  // Add case documents
  Array.from(caseDocuments.entries()).forEach(([fileId, fileData]) => {
    const fileItem = document.createElement('div');
    fileItem.className = 'file-item';
    fileItem.innerHTML = `
      <div class="file-name">${fileData.name}</div>
      <div class="file-type ${fileData.type}">${fileData.type.toUpperCase()}</div>
      <div class="file-category category-case">CASE DOC</div>
      <div class="file-size">${formatFileSize(fileData.size)}</div>
      <button type="button" class="file-remove" onclick="removeFile('${fileId}')">
        Remove
      </button>
    `;
    fileListContainer.appendChild(fileItem);
  });
}

function removeIntakeForm(): void {
  intakeForm = null;
  showIntakeStatus('⚠️ Please upload a client intake form to proceed.', 'error');
  updateFileDisplay();
  updateSubmitButton();
}

function removeFile(fileId: string): void {
  caseDocuments.delete(fileId);
  updateFileDisplay();
  updateSubmitButton();
}

function clearAllFiles(): void {
  intakeForm = null;
  caseDocuments.clear();
  showIntakeStatus('⚠️ Please upload a client intake form to proceed.', 'error');
  updateFileDisplay();
  updateSubmitButton();
}

function updateSubmitButton(): void {
  const totalSize = (intakeForm ? intakeForm.size : 0) + 
                   Array.from(caseDocuments.values()).reduce((sum, file) => sum + file.size, 0);
  const hasIntake = !!intakeForm;
  const hasCaseDocs = caseDocuments.size > 0;
  const underSizeLimit = totalSize <= MAX_FILE_SIZE;
  
  submitBtn.disabled = !hasIntake || !hasCaseDocs || !underSizeLimit;
  
  if (!hasIntake) {
    submitBtn.textContent = '⚠️ Upload Intake Form Required';
  } else if (!hasCaseDocs) {
    submitBtn.textContent = '⚠️ Upload Case Documents Required';
  } else if (!underSizeLimit) {
    submitBtn.textContent = '❌ File Size Limit Exceeded';
  } else {
    submitBtn.textContent = `🚀 Generate Analysis (${caseDocuments.size + 1} documents)`;
  }
}

// Form submission handler
async function handleSubmit(e: Event): Promise<void> {
  e.preventDefault();
  
  if (!intakeForm) {
    showStatus('⚠️ Please upload the client intake form.', 'error');
    return;
  }
  
  if (caseDocuments.size === 0) {
    showStatus('⚠️ Please upload at least one case document.', 'error');
    return;
  }

  const form = document.getElementById('uploadForm') as HTMLFormElement;
  if (!form) {
    console.error('Form with ID "uploadForm" not found');
    showStatus('❌ System Error: Form not found. Please refresh the page.', 'error');
    return;
  }

  // Create FormData object to capture all form fields automatically
  const formData = new FormData(form);
  
  // Add intake form file (override any existing intakeForm field)
  formData.set('intakeForm', intakeForm.file);
  
  // Add case documents
  let fileIndex = 0;
  caseDocuments.forEach((fileData) => {
    formData.append(`caseDocument${fileIndex}`, fileData.file);
    fileIndex++;
  });
  
  // Show processing status
  showStatus(`🔄 Analyzing intake form and ${caseDocuments.size} case documents... This process may take several minutes.`, 'processing');
  submitBtn.disabled = true;
  submitBtn.textContent = '⏳ Generating Legal Analysis...';
  
  console.log('Submitting form data to n8n webhook...');
  console.log('Webhook URL:', WEBHOOK_URL);
  console.log('Form data entries:', Array.from(formData.entries()).map(([key, value]) =>
    value instanceof File ? [key, `File: ${value.name} (${value.size} bytes)`] : [key, value]
  ));
  
  try {
    // Send POST request using fetch API
    const response = await fetch(WEBHOOK_URL, {
      method: 'POST',
      body: formData
      // Deliberately NOT setting Content-Type header to allow browser
      // to set correct multipart/form-data boundary automatically
    });
    
    // Log response details
    console.log('Server response status:', response.status, response.statusText);
    console.log('Response headers:', Object.fromEntries(response.headers.entries()));
    
    // Check if response has content before parsing JSON
    const contentLength = response.headers.get('content-length');
    let result: AnalysisResult | null = null;
    
    if (contentLength && contentLength !== '0') {
      try {
        result = await response.json();
        console.log('Server response:', result);
      } catch (jsonError) {
        console.warn('Failed to parse JSON response:', jsonError);
        console.log('Response text:', await response.clone().text());
      }
    } else {
      console.log('Server returned empty response (content-length: 0)');
    }
    
    console.log('Submission successful:', response.ok);
    
    if (response.ok) {
      // If we have a successful response, consider it a success regardless of JSON content
      if (result && result.status === 'success') {
        // Handle full response with result data
        showStatus(`✅ Legal Analysis Complete! Generated professional findings letter and comprehensive case analysis for ${result.documentsProcessed} documents.`, 'success');
        
        // Create download links for generated files
        if (result.downloadLinks) {
          const downloadHtml = `
            <div style="margin-top: 20px; padding: 20px; background: #f0f9ff; border-radius: 8px;">
              <h4 style="color: #1e40af; margin-bottom: 15px;">📥 Download Generated Legal Documents:</h4>
              <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                <a href="${result.downloadLinks.findingsLetter}" target="_blank" style="background: #059669; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">📧 Professional Findings Letter</a>
                <a href="${result.downloadLinks.caseAnalysis}" target="_blank" style="background: #0284c7; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">📊 Detailed Case Analysis</a>
                <a href="${result.downloadLinks.executiveSummary}" target="_blank" style="background: #7c3aed; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600;">📋 Executive Summary</a>
              </div>
            </div>
          `;
          statusElement.innerHTML += downloadHtml;
        }
      } else {
        // Handle successful HTTP response but no detailed result data
        const totalFiles = caseDocuments.size + 1; // +1 for intake form
        showStatus(`✅ Form submitted successfully! Your legal documents (${totalFiles} files) have been uploaded to the analysis system. Processing will begin shortly.`, 'success');
      }
      
      console.log('Form submitted successfully to n8n webhook');
    } else {
      console.error('Server returned error:', response.status, response.statusText);
      if (result) {
        console.error('Error response:', result);
        showStatus(`❌ Analysis Failed: ${result.message || 'Unknown error occurred during document processing.'}`, 'error');
      } else {
        showStatus(`❌ Server Error: HTTP ${response.status} ${response.statusText}`, 'error');
      }
      throw new Error(`Server error: ${response.status} ${response.statusText}`);
    }
  } catch (error) {
    // Log any errors with comprehensive details
    console.error('Error submitting form to n8n webhook:', error);
    console.error('Error details:', {
      message: error instanceof Error ? error.message : 'Unknown error',
      name: error instanceof Error ? error.name : 'Unknown',
      stack: error instanceof Error ? error.stack : undefined
    });
    
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    showStatus(`❌ System Error: ${errorMessage}. Please try again or contact technical support.`, 'error');
    throw error;
  } finally {
    updateSubmitButton();
  }
}

function showStatus(message: string, type: string): void {
  statusElement.innerHTML = message;
  statusElement.className = `status ${type}`;
  statusElement.style.display = 'block';
  
  // Scroll to status message
  statusElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Make functions globally available for onclick handlers
(window as any).removeIntakeForm = removeIntakeForm;
(window as any).removeFile = removeFile;
(window as any).clearAllFiles = clearAllFiles;

// Initialize the application
function initializeApp(): void {
  // Get DOM elements that already exist in the HTML
  intakeUploadSection = document.getElementById('intakeUploadSection') as HTMLElement;
  documentsUploadSection = document.getElementById('documentsUploadSection') as HTMLElement;
  intakeInput = document.getElementById('intakeInput') as HTMLInputElement;
  documentsInput = document.getElementById('documentsInput') as HTMLInputElement;
  intakeStatus = document.getElementById('intakeStatus') as HTMLElement;
  fileManager = document.getElementById('fileManager') as HTMLElement;
  fileListContainer = document.getElementById('fileListContainer') as HTMLElement;
  submitBtn = document.getElementById('submitBtn') as HTMLButtonElement;
  statusElement = document.getElementById('status') as HTMLElement;
  sizeWarning = document.getElementById('sizeWarning') as HTMLElement;
  
  if (!intakeUploadSection || !documentsUploadSection || !intakeInput || !documentsInput || 
      !intakeStatus || !fileManager || !fileListContainer || !submitBtn || !statusElement || !sizeWarning) {
    console.error('Required DOM elements not found');
    return;
  }
  
  // Event listeners for drag and drop
  intakeUploadSection.addEventListener('dragover', (e) => handleDragOver(e, true));
  intakeUploadSection.addEventListener('dragleave', (e) => handleDragLeave(e, true));
  intakeUploadSection.addEventListener('drop', (e) => handleDrop(e, true));
  
  documentsUploadSection.addEventListener('dragover', (e) => handleDragOver(e, false));
  documentsUploadSection.addEventListener('dragleave', (e) => handleDragLeave(e, false));
  documentsUploadSection.addEventListener('drop', (e) => handleDrop(e, false));
  
  // File input event listeners
  intakeInput.addEventListener('change', (e) => handleFileSelect(e, true));
  documentsInput.addEventListener('change', (e) => handleFileSelect(e, false));
  
  // Form submission
  const form = document.getElementById('uploadForm') as HTMLFormElement;
  if (form) {
    form.addEventListener('submit', handleSubmit);
  }
  
  // Initialize status
  showIntakeStatus('⚠️ Please upload a client intake form to proceed.', 'error');
  
  console.log('Legal Document Analysis Portal initialized with enhanced UI');
}

// Start the application when the DOM is ready
document.addEventListener('DOMContentLoaded', initializeApp);