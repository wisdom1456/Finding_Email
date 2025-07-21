import { ComponentProps, StatusType, AnalysisResult } from './types.js';

export interface StatusDisplayProps extends ComponentProps {
  onStatusUpdate?: (message: string, type: StatusType) => void;
}

export function createStatusDisplay(props: StatusDisplayProps = {}): HTMLElement {
  const {
    className = '',
    id = 'statusDisplay'
  } = props;

  const statusElement = document.createElement('div');
  statusElement.className = `status ${className}`.trim();
  if (id) statusElement.id = id;
  statusElement.style.display = 'none'; // Initially hidden

  return statusElement;
}

export function showStatus(
  statusElement: HTMLElement, 
  message: string, 
  type: StatusType,
  result?: AnalysisResult
): void {
  statusElement.innerHTML = message;
  statusElement.className = `status ${type}`;
  statusElement.style.display = 'block';

  // Add download links if this is a successful result with download links
  if (type === 'success' && result?.downloadLinks) {
    const downloadHtml = `
      <div style="margin-top: 20px; padding: 20px; background: #f0f9ff; border-radius: 8px;">
        <h4 style="color: #1e40af; margin-bottom: 15px;">📥 Download Generated Files:</h4>
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
          <a href="${result.downloadLinks.findingsLetter}" target="_blank" style="background: #059669; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px;">📧 Findings Letter</a>
          <a href="${result.downloadLinks.caseAnalysis}" target="_blank" style="background: #0284c7; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px;">📊 Case Analysis</a>
          <a href="${result.downloadLinks.executiveSummary}" target="_blank" style="background: #7c3aed; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px;">📋 Executive Summary</a>
        </div>
      </div>
    `;
    statusElement.innerHTML += downloadHtml;
  }

  // Scroll to status message
  statusElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

export function hideStatus(statusElement: HTMLElement): void {
  statusElement.style.display = 'none';
  statusElement.innerHTML = '';
  statusElement.className = 'status';
}

export function createSubmitButton(props: {
  onSubmit: (e: Event) => void;
  className?: string;
  id?: string;
}): HTMLButtonElement {
  const {
    onSubmit,
    className = '',
    id = 'submitBtn'
  } = props;

  const submitButton = document.createElement('button');
  submitButton.type = 'submit';
  submitButton.className = `submit-btn ${className}`.trim();
  if (id) submitButton.id = id;
  submitButton.textContent = '🚀 Begin Document Analysis (No Files Selected)';

  submitButton.addEventListener('click', onSubmit);

  return submitButton;
}

export function updateSubmitButton(
  submitButton: HTMLButtonElement, 
  fileCount: number, 
  isUnderSizeLimit: boolean
): void {
  const hasFiles = fileCount > 0;
  
  submitButton.disabled = !hasFiles || !isUnderSizeLimit;
  
  if (!hasFiles) {
    submitButton.textContent = '🚀 Begin Document Analysis (No Files Selected)';
  } else if (!isUnderSizeLimit) {
    submitButton.textContent = '❌ File Size Limit Exceeded';
  } else {
    submitButton.textContent = `🚀 Analyze ${fileCount} Documents`;
  }
}

export function setSubmitButtonProcessing(submitButton: HTMLButtonElement, isProcessing: boolean): void {
  if (isProcessing) {
    submitButton.disabled = true;
    submitButton.textContent = '⏳ Analysis in Progress...';
  } else {
    submitButton.disabled = false;
    // Button text will be updated by updateSubmitButton
  }
}

// StatusDisplay component styles (to be moved to shared styles later)
export const statusDisplayStyles = `
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
`;