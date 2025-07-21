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
  message: string;
  documentsProcessed: number;
  successfulBranches: number;
  downloadLinks: {
    findingsLetter: string;
    caseAnalysis: string;
    executiveSummary: string;
  };
  emailDetails: {
    subject: string;
    from: string;
    to: string;
    bodyLength: number;
    emlFileName: string;
    txtFileName: string;
  };
  caseInfo: {
    caseId: string;
    clientName: string;
    attorneyName: string;
    caseReference: string;
  };
  completedAt: string;
  analysisComplete: boolean;
  documentsGenerated: boolean;
  readyForDownload: boolean;
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