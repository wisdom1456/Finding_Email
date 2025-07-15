import { ComponentProps, FileUploadCallbacks } from './types.js';

export interface FileUploadProps extends ComponentProps {
  callbacks: FileUploadCallbacks;
  maxFileSize?: number;
  supportedTypes?: string[];
}

export function createFileUpload(props: FileUploadProps): HTMLElement {
  const {
    callbacks,
    supportedTypes = ['pdf', 'docx', 'doc', 'txt'],
    className = '',
    id = ''
  } = props;

  const fileUploadElement = document.createElement('div');
  fileUploadElement.className = `form-section file-upload ${className}`.trim();
  if (id) fileUploadElement.id = id;

  fileUploadElement.innerHTML = `
    <h3>📁 Document Upload</h3>
    
    <div class="folder-structure">
      <h4>📂 Standard Client Folder Structure:</h4>
      <div class="folder-tree">
Client Name []/<br>
├── 📁 Atty Notes<br>
├── 📁 Atty Work Product<br>
├── 📁 Client Docs<br>
├── 📁 Correspondence<br>
├── 📁 Demand<br>
├── 📁 Drafts<br>
└── 📁 Shared Folder with Client
      </div>
      <p style="margin-top: 10px; color: #6b7280; font-size: 13px;">
        Upload all relevant documents from these folders for comprehensive case analysis
      </p>
    </div>
    
    <div class="upload-section" id="uploadSection">
      <div class="upload-icon">📄</div>
      <div class="upload-text">Drag & Drop Files or Folders Here</div>
      <div style="font-size: 16px; color: #6b7280; margin-bottom: 20px;">
        or use the buttons below to select files
      </div>
      
      <div class="upload-options">
        <button type="button" class="upload-btn" id="selectFilesBtn">
          📄 Select Individual Files
        </button>
        <button type="button" class="upload-btn" id="selectFolderBtn">
          📁 Select Entire Folder
        </button>
      </div>
      
      <div style="font-size: 14px; color: #6b7280; margin-top: 15px;">
        <strong>Supported formats:</strong> PDF, DOCX, DOC, TXT<br>
        <strong>Maximum total size:</strong> 100MB
      </div>
    </div>
    
    <input type="file" id="fileInput" multiple accept=".pdf,.docx,.doc,.txt" style="display: none;">
    <input type="file" id="folderInput" webkitdirectory multiple style="display: none;">
  `;

  // Get DOM elements
  const uploadSection = fileUploadElement.querySelector('#uploadSection') as HTMLElement;
  const fileInput = fileUploadElement.querySelector('#fileInput') as HTMLInputElement;
  const folderInput = fileUploadElement.querySelector('#folderInput') as HTMLInputElement;
  const selectFilesBtn = fileUploadElement.querySelector('#selectFilesBtn') as HTMLButtonElement;
  const selectFolderBtn = fileUploadElement.querySelector('#selectFolderBtn') as HTMLButtonElement;

  // Event handlers
  function handleDragOver(e: DragEvent): void {
    e.preventDefault();
    uploadSection.classList.add('dragover');
  }

  function handleDragLeave(e: DragEvent): void {
    e.preventDefault();
    uploadSection.classList.remove('dragover');
  }

  function handleDrop(e: DragEvent): void {
    e.preventDefault();
    uploadSection.classList.remove('dragover');
    
    if (e.dataTransfer?.files) {
      const files = Array.from(e.dataTransfer.files);
      processFiles(files);
    }
  }

  function handleFileSelect(e: Event): void {
    const target = e.target as HTMLInputElement;
    if (target.files) {
      const files = Array.from(target.files);
      processFiles(files);
      
      // Reset the input so the same files can be selected again if needed
      target.value = '';
    }
  }

  function processFiles(files: File[]): void {
    const validFiles = files.filter(file => {
      const extension = file.name.split('.').pop()?.toLowerCase();
      return extension && supportedTypes.includes(extension);
    });

    if (validFiles.length !== files.length) {
      const skippedCount = files.length - validFiles.length;
      console.warn(`Skipped ${skippedCount} unsupported files. Supported types: ${supportedTypes.join(', ')}`);
    }

    if (validFiles.length > 0) {
      callbacks.onFilesAdded(validFiles);
    }
  }

  // Attach event listeners
  uploadSection.addEventListener('dragover', handleDragOver);
  uploadSection.addEventListener('dragleave', handleDragLeave);
  uploadSection.addEventListener('drop', handleDrop);
  
  fileInput.addEventListener('change', handleFileSelect);
  folderInput.addEventListener('change', handleFileSelect);
  
  selectFilesBtn.addEventListener('click', () => fileInput.click());
  selectFolderBtn.addEventListener('click', () => folderInput.click());

  return fileUploadElement;
}

// FileUpload component styles (to be moved to shared styles later)
export const fileUploadStyles = `
  .folder-structure {
    background: #f0f9ff;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    padding: 15px;
    margin: 20px 0;
    font-size: 14px;
  }
  
  .folder-structure h4 {
    color: #1e40af;
    margin-bottom: 10px;
  }
  
  .folder-tree {
    font-family: monospace;
    color: #374151;
    line-height: 1.4;
  }
  
  .upload-section {
    background: #f8fafc;
    border: 3px dashed #3b82f6;
    border-radius: 15px;
    padding: 40px;
    text-align: center;
    transition: all 0.3s ease;
    position: relative;
    min-height: 200px;
  }
  
  .upload-section.dragover {
    background: #eff6ff;
    border-color: #1d4ed8;
    transform: scale(1.02);
  }
  
  .upload-icon {
    font-size: 4em;
    color: #3b82f6;
    margin-bottom: 20px;
    display: block;
  }
  
  .upload-text {
    font-size: 1.2em;
    color: #4b5563;
    margin-bottom: 20px;
    font-weight: 600;
  }
  
  .upload-options {
    display: flex;
    gap: 20px;
    justify-content: center;
    margin: 20px 0;
  }
  
  .upload-btn {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
    color: white;
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  
  .upload-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.3);
  }
  
  @media (max-width: 768px) {
    .upload-options {
      flex-direction: column;
      align-items: center;
    }
  }
`;