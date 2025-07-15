import { ComponentProps, CaseFormData } from './types.js';

export interface CaseFormProps extends ComponentProps {
  onFormDataChange?: (data: CaseFormData) => void;
  initialData?: Partial<CaseFormData>;
}

export function createCaseForm(props: CaseFormProps = {}): HTMLElement {
  const {
    onFormDataChange,
    initialData = {},
    className = '',
    id = ''
  } = props;

  const caseFormElement = document.createElement('div');
  caseFormElement.className = `form-section case-form ${className}`.trim();
  if (id) caseFormElement.id = id;

  caseFormElement.innerHTML = `
    <h3>📋 Case Information</h3>
    <div class="form-row">
      <div class="form-group">
        <label for="clientName">Client Name *</label>
        <input type="text" id="clientName" name="clientName" required value="${initialData.clientName || ''}">
      </div>
      <div class="form-group">
        <label for="caseReference">Case Reference</label>
        <input type="text" id="caseReference" name="caseReference" placeholder="CASE-2024-001" value="${initialData.caseReference || ''}">
      </div>
      <div class="form-group">
        <label for="attorneyName">Responsible Attorney *</label>
        <input type="text" id="attorneyName" name="attorneyName" required value="${initialData.attorneyName || ''}">
      </div>
    </div>
  `;

  // Add event listeners for form data changes
  if (onFormDataChange) {
    const inputs = caseFormElement.querySelectorAll('input');
    inputs.forEach(input => {
      input.addEventListener('input', () => {
        const formData = getCaseFormData(caseFormElement);
        onFormDataChange(formData);
      });
    });
  }

  return caseFormElement;
}

export function getCaseFormData(formElement: HTMLElement): CaseFormData {
  const clientName = (formElement.querySelector('#clientName') as HTMLInputElement)?.value || '';
  const caseReference = (formElement.querySelector('#caseReference') as HTMLInputElement)?.value || '';
  const attorneyName = (formElement.querySelector('#attorneyName') as HTMLInputElement)?.value || '';

  return {
    clientName,
    caseReference,
    attorneyName
  };
}

export function validateCaseForm(formData: CaseFormData): { isValid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!formData.clientName.trim()) {
    errors.push('Client Name is required');
  }

  if (!formData.attorneyName.trim()) {
    errors.push('Responsible Attorney is required');
  }

  return {
    isValid: errors.length === 0,
    errors
  };
}

// CaseForm component styles (to be moved to shared styles later)
export const caseFormStyles = `
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
  
  @media (max-width: 768px) {
    .form-row {
      grid-template-columns: 1fr;
    }
  }
`;