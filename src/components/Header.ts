import { ComponentProps } from './types.js';

export interface HeaderProps extends ComponentProps {
  firmName?: string;
  tagline?: string;
  logoIcon?: string;
}

export function createHeader(props: HeaderProps = {}): HTMLElement {
  const {
    firmName = 'Your Law Firm Name',
    tagline = 'Excellence in Legal Document Analysis',
    logoIcon = '⚖️',
    className = '',
    id = ''
  } = props;

  const headerElement = document.createElement('div');
  headerElement.className = `header ${className}`.trim();
  if (id) headerElement.id = id;

  headerElement.innerHTML = `
    <div class="firm-logo">${logoIcon} ${firmName}</div>
    <div class="firm-tagline">${tagline}</div>
  `;

  return headerElement;
}

// Header component styles (to be moved to shared styles later)
export const headerStyles = `
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
`;