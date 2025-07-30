// Configuration
const WEBHOOK_URL = 'http://localhost:8000/api/legal-analysis-upload'; // Will be replaced with Railway URL
const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB in bytes

import { AnalysisResult } from './components/types';

// Type definitions
interface FileData {
  file: File;
  name: string;
  size: number;
  type: string;
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

  // Create FormData object and manually add all fields
  const formData = new FormData();
  
  // Add text form fields manually
  formData.append('clientName', (document.getElementById('clientName') as HTMLInputElement).value);
  formData.append('caseReference', (document.getElementById('caseReference') as HTMLInputElement).value);
  formData.append('attorneyName', (document.getElementById('attorneyName') as HTMLInputElement).value);
  
  // Add all files under the 'files' key
  formData.append('files', intakeForm.file);
  caseDocuments.forEach((fileData) => {
    formData.append('files', fileData.file);
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
    });
    
    // Parse JSON response
    let result: AnalysisResult | null = null;
    
    if (response.ok) {
      try {
        let rawResult = await response.json();
        console.log('Full n8n response:', rawResult);

        // The new FastAPI backend returns the JSON directly
        result = rawResult;
        
      } catch (jsonError) {
        console.warn('Failed to parse JSON response:', jsonError);
        result = null;
      }
      
      // Check if we got the expected response format
      if (result && result.status === 'success') {
        // Show success message
        showStatus(result.message, 'success');
        
        // CRITICAL: Check for downloadLinks
        if (result.downloadLinks) {
          console.log('Download links found:', result.downloadLinks); // DEBUG LINE
          
          // Create download section
          const downloadHtml = `
            <div style="margin-top: 20px; padding: 20px; background: #f0f9ff; border-radius: 8px; border: 1px solid #bfdbfe;">
              <h4 style="color: #1e40af; margin-bottom: 15px; font-size: 18px;">📥 Download Generated Files</h4>
              <div style="display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 15px;">
                <a href="${result.downloadLinks.findingsLetter}"
                   download="${result.emailDetails?.emlFileName || 'findings-letter.eml'}"
                   style="background: #059669; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">
                   📧 Email Letter (.eml)
                </a>
                <a href="${result.downloadLinks.caseAnalysis}"
                   download="${result.emailDetails?.txtFileName || 'case-analysis.txt'}"
                   style="background: #0284c7; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">
                   📄 Text Format (.txt)
                </a>
                <a href="${result.downloadLinks.executiveSummary}"
                   download="executive-summary.txt"
                   style="background: #7c3aed; color: white; padding: 12px 20px; text-decoration: none; border-radius: 6px; font-weight: 600; display: inline-block;">
                   📋 Summary (.txt)
                </a>
              </div>
              <p style="margin: 10px 0 0 0; color: #4b5563; font-size: 14px; line-height: 1.4;">
                💡 <strong>How to use:</strong> Click ".eml" to import into your email client, or click ".txt" to download text you can copy/paste.
              </p>
            </div>
          `;
          
          // Add download section to the status element
          statusElement.innerHTML += downloadHtml;
        } else {
          console.error('No downloadLinks in response. Full result:', result);
          // Still show success but note missing downloads
          statusElement.innerHTML += '<p style="color: #f59e0b; margin-top: 10px;">⚠️ Analysis completed but download links not available.</p>';
        }
      } else {
        // Handle non-success response
        const errorMsg = result?.message || 'Analysis completed but response format unexpected';
        showStatus(`⚠️ ${errorMsg}`, 'error');
        console.error('Unexpected response format:', result);
      }
    } else {
      // Handle HTTP errors
      showStatus(`❌ Server Error: HTTP ${response.status} ${response.statusText}`, 'error');
    }
    
  } catch (error) {
    console.error('Error submitting form:', error);
    showStatus(`❌ System Error: ${(error as Error).message}`, 'error');
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