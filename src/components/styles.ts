// Shared styles for all components
export function injectStyles(): void {
  const styleElement = document.createElement('style');
  styleElement.textContent = allStyles;
  document.head.appendChild(styleElement);
}

export const allStyles = `
  /* Base Styles */
  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }
  
  body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
    min-height: 100vh;
    padding: 20px;
  }
  
  /* Container Styles */
  .container {
    max-width: 1200px;
    margin: 0 auto;
    background: white;
    border-radius: 15px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    overflow: hidden;
  }
  
  .form-content {
    padding: 40px;
  }
  
  .hidden {
    display: none;
  }
  
  /* Header Component Styles */
  .header {
    text-align: center;
    color: white;
    margin-bottom: 30px;
  }
  
  .firm-logo {
    font-size: 2.5em;
    font-weight: bold;
    margin-bottom: 10px;
  }
  
  .firm-tagline {
    font-size: 1.1em;
    opacity: 0.9;
    font-style: italic;
  }
  
  /* FormHeader Component Styles */
  .form-header {
    background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
    color: white;
    padding: 30px;
    text-align: center;
  }
  
  .form-header h1 {
    font-size: 2em;
    margin-bottom: 10px;
  }
  
  .form-header p {
    opacity: 0.9;
    font-size: 1.1em;
  }
  
  /* Form Section and CaseForm Component Styles */
  .form-section {
    margin-bottom: 30px;
  }
  
  .form-section h3 {
    color: #1f2937;
    margin-bottom: 15px;
    font-size: 1.3em;
    border-bottom: 2px solid #e5e7eb;
    padding-bottom: 8px;
  }
  
  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }
  
  .form-group {
    margin-bottom: 20px;
  }
  
  label {
    display: block;
    margin-bottom: 8px;
    font-weight: 600;
    color: #374151;
  }
  
  input[type="text"] {
    width: 100%;
    padding: 12px 16px;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    font-size: 16px;
    transition: all 0.3s ease;
  }
  
  input[type="text"]:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
  
  /* FileUpload Component Styles */
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
  
  /* FileManager Component Styles */
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
  
  /* StatusDisplay Component Styles */
  .status {
    margin-top: 25px;
    padding: 20px;
    border-radius: 8px;
    display: none;
    font-weight: 500;
  }
  
  .status.success {
    background: #d1fae5;
    color: #065f46;
    border: 1px solid #a7f3d0;
  }
  
  .status.error {
    background: #fee2e2;
    color: #991b1b;
    border: 1px solid #fca5a5;
  }
  
  .status.processing {
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #fcd34d;
  }
  
  .submit-btn {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    color: white;
    padding: 18px 40px;
    border: none;
    border-radius: 10px;
    font-size: 18px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    width: 100%;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 20px;
  }
  
  .submit-btn:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(5, 150, 105, 0.3);
  }
  
  .submit-btn:disabled {
    background: #9ca3af;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }
  
  /* Responsive Design */
  @media (max-width: 768px) {
    .form-row {
      grid-template-columns: 1fr;
    }
    
    .upload-options {
      flex-direction: column;
      align-items: center;
    }
    
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