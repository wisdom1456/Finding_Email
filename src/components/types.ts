// Shared type definitions for components
export interface FileData {
  file: File;
  name: string;
  size: number;
  type: string;
  path: string;
  folder: string;
}

export interface AnalysisResult {
  status: string;
  message?: string;
  documentsProcessed?: number;
  downloadLinks?: {
    findingsEmail: string;
    summaryReport: string;
    quickSummary: string;
  };
}

export interface CaseFormData {
  clientName: string;
  caseReference: string;
  attorneyName: string;
}

export interface ComponentProps {
  className?: string;
  id?: string;
}

export interface FileUploadCallbacks {
  onFilesAdded: (files: File[]) => void;
  onFileRemoved: (fileId: string) => void;
  onClearAll: () => void;
}

export interface StatusCallbacks {
  onStatusUpdate: (message: string, type: string) => void;
}

export type StatusType = 'success' | 'error' | 'processing';