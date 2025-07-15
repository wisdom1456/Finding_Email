import { ComponentProps } from './types.js';

export interface FormHeaderProps extends ComponentProps {
  title?: string;
  description?: string;
  icon?: string;
}

export function createFormHeader(props: FormHeaderProps = {}): HTMLElement {
  const {
    title = 'Legal Case Document Analysis',
    description = 'Upload all case documents for comprehensive AI-powered legal analysis',
    icon = '🔍',
    className = '',
    id = ''
  } = props;

  const formHeaderElement = document.createElement('div');
  formHeaderElement.className = `form-header ${className}`.trim();
  if (id) formHeaderElement.id = id;

  formHeaderElement.innerHTML = `
    <h1>${icon} ${title}</h1>
    <p>${description}</p>
  `;

  return formHeaderElement;
}

// FormHeader component styles (to be moved to shared styles later)
export const formHeaderStyles = `
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
`;