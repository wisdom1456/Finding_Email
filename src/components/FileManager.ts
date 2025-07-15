import { ComponentProps, FileData, FileUploadCallbacks } from './types.js';

export interface FileManagerProps extends ComponentProps {
  files: Map<string, FileData>;
  callbacks: FileUploadCallbacks;
  maxFileSize?: number;
}

export function createFileManager(props: FileManagerProps): HTMLElement {
  const {
    files,
    callbacks,
    maxFileSize = 100 * 1024 * 1024, // 100MB
    className = '',
    id = ''
  } = props;

  const fileManagerElement = document.createElement('div');
  fileManagerElement.className = `file-manager ${className}`.trim();
  if (id) fileManagerElement.id = id;
  
  // Initially hidden if no files
  fileManagerElement.style.display = files.size === 0 ? 'none' : 'block';

  fileManagerElement.innerHTML = `
    <div class="form-section">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
        <h3>📊 Uploaded Files</h3>
        <button type="button" class="clear-all-btn" id="clearAllBtn">
          🗑️ Clear All Files
        </button>
      </div>
      
      <div class="file-summary">
        <div class="file-stats">
          <div class="stat-item">
            <div class="stat-number" id="totalFiles">0</div>
            <div class="stat-label">Total Files</div>
          </div>
          <div class="stat-item">
            <div class="stat-number" id="totalSize">0 B</div>
            <div class="stat-label">Total Size</div>
          </div>
          <div class="stat-item">
            <div class="stat-number" id="fileTypes">0</div>
            <div class="stat-label">File Types</div>
          </div>
          <div class="stat-item">
            <div class="stat-number" id="folderCount">0</div>
            <div class="stat-label">Folders</div>
          </div>
        </div>
        <div class="size-warning" id="sizeWarning" style="display: none;"></div>
      </div>
      
      <div class="file-list">
        <div class="file-list-header">
          <div>File Name & Path</div>
          <div>Type</div>
          <div>Size</div>
          <div>Folder</div>
          <div>Action</div>
        </div>
        <div id="fileListContainer">
          <!-- File items will be dynamically inserted here -->
        </div>
      </div>
    </div>
  `;

  // Get DOM elements for dynamic updates
  const clearAllBtn = fileManagerElement.querySelector('#clearAllBtn') as HTMLButtonElement;
  fileManagerElement.querySelector('#fileListContainer') as HTMLElement;

  // Attach event listeners
  clearAllBtn.addEventListener('click', () => {
    callbacks.onClearAll();
  });

  // Initial render
  updateFileDisplay(fileManagerElement, files, maxFileSize, callbacks.onFileRemoved);

  return fileManagerElement;
}

export function updateFileDisplay(
  fileManagerElement: HTMLElement, 
  files: Map<string, FileData>, 
  maxFileSize: number,
  onFileRemoved: (fileId: string) => void
): void {
  // Show/hide file manager based on whether files exist
  if (files.size === 0) {
    fileManagerElement.style.display = 'none';
    return;
  }
  
  fileManagerElement.style.display = 'block';

  // Calculate statistics
  const totalSize = Array.from(files.values()).reduce((sum, file) => sum + file.size, 0);
  const fileTypes = new Set(Array.from(files.values()).map(file => file.type));
  const folders = new Set(Array.from(files.values()).map(file => file.folder));

  // Update statistics display
  const totalFilesEl = fileManagerElement.querySelector('#totalFiles') as HTMLElement;
  const totalSizeEl = fileManagerElement.querySelector('#totalSize') as HTMLElement;
  const fileTypesEl = fileManagerElement.querySelector('#fileTypes') as HTMLElement;
  const folderCountEl = fileManagerElement.querySelector('#folderCount') as HTMLElement;
  const sizeWarning = fileManagerElement.querySelector('#sizeWarning') as HTMLElement;

  if (totalFilesEl) totalFilesEl.textContent = files.size.toString();
  if (totalSizeEl) totalSizeEl.textContent = formatFileSize(totalSize);
  if (fileTypesEl) fileTypesEl.textContent = fileTypes.size.toString();
  if (folderCountEl) folderCountEl.textContent = folders.size.toString();

  // Handle size warnings
  if (sizeWarning) {
    if (totalSize > maxFileSize * 0.8) {
      sizeWarning.style.display = 'block';
      if (totalSize > maxFileSize) {
        sizeWarning.textContent = '❌ Total file size exceeds 100MB limit. Please remove some files.';
        sizeWarning.classList.add('size-error');
      } else {
        sizeWarning.textContent = '⚠️ Total file size is approaching the 100MB limit';
        sizeWarning.classList.remove('size-error');
      }
    } else {
      sizeWarning.style.display = 'none';
    }
  }

  // Update file list
  const fileListContainer = fileManagerElement.querySelector('#fileListContainer') as HTMLElement;
  if (fileListContainer) {
    fileListContainer.innerHTML = '';
    
    Array.from(files.entries()).forEach(([fileId, fileData]) => {
      const fileItem = createFileItem(fileId, fileData, onFileRemoved);
      fileListContainer.appendChild(fileItem);
    });
  }
}

function createFileItem(fileId: string, fileData: FileData, onFileRemoved: (fileId: string) => void): HTMLElement {
  const fileItem = document.createElement('div');
  fileItem.className = 'file-item';
  
  fileItem.innerHTML = `
    <div>
      <div class="file-name">${fileData.name}</div>
      <div class="file-path">${fileData.path}</div>
    </div>
    <div class="file-type ${fileData.type}">${fileData.type}</div>
    <div class="file-size">${formatFileSize(fileData.size)}</div>
    <div>${fileData.folder}</div>
    <button type="button" class="file-remove" data-file-id="${fileId}">
      Remove
    </button>
  `;

  // Add event listener for remove button
  const removeBtn = fileItem.querySelector('.file-remove') as HTMLButtonElement;
  removeBtn.addEventListener('click', () => {
    onFileRemoved(fileId);
  });

  return fileItem;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// FileManager component styles (to be moved to shared styles later)
export const fileManagerStyles = `
  .file-manager {
    margin-top: 30px;
  }
  
  .file-summary {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
  }
  
  .file-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 15px;
    margin-bottom: 15px;
  }
  
  .stat-item {
    text-align: center;
    padding: 10px;
    background: white;
    border-radius: 6px;
    border: 1px solid #e5e7eb;
  }
  
  .stat-number {
    font-size: 1.5em;
    font-weight: bold;
    color: #3b82f6;
  }
  
  .stat-label {
    font-size: 0.9em;
    color: #6b7280;
    margin-top: 5px;
  }
  
  .size-warning {
    background: #fef3c7;
    color: #92400e;
    padding: 10px;
    border-radius: 6px;
    margin-top: 10px;
    display: none;
  }
  
  .size-error {
    background: #fee2e2;
    color: #991b1b;
  }
  
  .file-list {
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: white;
  }
  
  .file-list-header {
    background: #f9fafb;
    padding: 12px;
    border-bottom: 1px solid #e5e7eb;
    font-weight: 600;
    color: #374151;
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr auto;
    gap: 15px;
    align-items: center;
  }
  
  .file-item {
    padding: 12px;
    border-bottom: 1px solid #f3f4f6;
    display: grid;
    grid-template-columns: 2fr 1fr 1fr 1fr auto;
    gap: 15px;
    align-items: center;
    transition: background 0.2s ease;
  }
  
  .file-item:hover {
    background: #f9fafb;
  }
  
  .file-item:last-child {
    border-bottom: none;
  }
  
  .file-name {
    font-weight: 500;
    color: #374151;
    word-break: break-word;
  }
  
  .file-path {
    font-size: 0.85em;
    color: #6b7280;
    font-family: monospace;
  }
  
  .file-type {
    background: #e5e7eb;
    color: #374151;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 0.8em;
    font-weight: 600;
    text-transform: uppercase;
  }
  
  .file-type.pdf {
    background: #fecaca;
    color: #991b1b;
  }
  
  .file-type.docx,
  .file-type.doc {
    background: #bfdbfe;
    color: #1e40af;
  }
  
  .file-type.txt {
    background: #d1fae5;
    color: #065f46;
  }
  
  .file-size {
    color: #6b7280;
    font-size: 0.9em;
  }
  
  .file-remove {
    background: #fee2e2;
    color: #991b1b;
    border: none;
    border-radius: 4px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 0.8em;
    transition: all 0.2s ease;
  }
  
  .file-remove:hover {
    background: #fecaca;
  }
  
  .clear-all-btn {
    background: #f3f4f6;
    color: #374151;
    border: 1px solid #d1d5db;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9em;
    transition: all 0.2s ease;
  }
  
  .clear-all-btn:hover {
    background: #e5e7eb;
  }
  
  @media (max-width: 768px) {
    .file-list-header,
    .file-item {
      grid-template-columns: 1fr;
      gap: 10px;
    }
    
    .file-stats {
      grid-template-columns: 1fr 1fr;
    }
  }
`;