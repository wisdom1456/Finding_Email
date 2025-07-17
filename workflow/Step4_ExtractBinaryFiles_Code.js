// Step 4: Binary Data Reception and File Cataloging
// This node extracts binary files from webhook and creates file catalog

// Get the structured intake data from previous step
const intakeData = $input.first().json;

// Get the original webhook data that contains binary files
// We need to look back at the webhook node's output
const webhookItems = $items("Webhook");
const binaryData = webhookItems[0].binary || {};

// Initialize file processing results
const fileProcessingResult = {
  isValid: true,
  errors: [],
  filesCatalog: {
    intakeForm: null,
    caseDocuments: [],
    totalFileSize: 0,
    fileCount: 0
  },
  structuredData: intakeData.structuredData || {},
  processingTimestamp: new Date().toISOString()
};

// Check if we have any binary data
if (!binaryData || Object.keys(binaryData).length === 0) {
  fileProcessingResult.isValid = false;
  fileProcessingResult.errors.push("No files were uploaded with the form submission");
  return [{ json: fileProcessingResult }];
}

// Define allowed file types
const allowedMimeTypes = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
  'application/msword', // .doc
  'text/plain' // .txt
];

// Size limit: 100MB total
const MAX_TOTAL_SIZE = 100 * 1024 * 1024; // 100MB in bytes
let totalSize = 0;

// Process intake form (required)
if (binaryData.intakeForm) {
  const intakeFile = binaryData.intakeForm;
  
  // Validate file type
  if (!allowedMimeTypes.includes(intakeFile.mimeType)) {
    fileProcessingResult.errors.push(`Intake form has invalid file type: ${intakeFile.mimeType}`);
  }
  
  // Extract metadata
  fileProcessingResult.filesCatalog.intakeForm = {
    fileName: intakeFile.fileName,
    fileSize: intakeFile.fileSize,
    mimeType: intakeFile.mimeType,
    uploadedAt: new Date().toISOString()
  };
  
  totalSize += intakeFile.fileSize;
  fileProcessingResult.filesCatalog.fileCount++;
} else {
  fileProcessingResult.isValid = false;
  fileProcessingResult.errors.push("Required intake form is missing");
}

// Process case documents
let documentIndex = 0;
let hasAtLeastOneDocument = false;

while (binaryData[`caseDocument${documentIndex}`]) {
  const docFile = binaryData[`caseDocument${documentIndex}`];
  hasAtLeastOneDocument = true;
  
  // Validate file type
  if (!allowedMimeTypes.includes(docFile.mimeType)) {
    fileProcessingResult.errors.push(`Case document ${documentIndex} has invalid file type: ${docFile.mimeType}`);
  }
  
  // Add to catalog
  fileProcessingResult.filesCatalog.caseDocuments.push({
    index: documentIndex,
    fileName: docFile.fileName,
    fileSize: docFile.fileSize,
    mimeType: docFile.mimeType,
    uploadedAt: new Date().toISOString()
  });
  
  totalSize += docFile.fileSize;
  fileProcessingResult.filesCatalog.fileCount++;
  documentIndex++;
}

// Validate at least one case document
if (!hasAtLeastOneDocument) {
  fileProcessingResult.isValid = false;
  fileProcessingResult.errors.push("At least one case document is required");
}

// Check total size limit
fileProcessingResult.filesCatalog.totalFileSize = totalSize;
if (totalSize > MAX_TOTAL_SIZE) {
  fileProcessingResult.isValid = false;
  fileProcessingResult.errors.push(`Total file size (${(totalSize / 1024 / 1024).toFixed(2)}MB) exceeds 100MB limit`);
}

// If there are validation errors, mark as invalid
if (fileProcessingResult.errors.length > 0) {
  fileProcessingResult.isValid = false;
}

// Merge with intake data if valid
if (fileProcessingResult.isValid && intakeData.isValid) {
  fileProcessingResult.message = "Files successfully received and cataloged";
  fileProcessingResult.structuredData.filesCatalog = fileProcessingResult.filesCatalog;
  fileProcessingResult.structuredData.dataProcessingStatus.filesProcessed = true;
  fileProcessingResult.structuredData.dataProcessingStatus.filesProcessedAt = new Date().toISOString();
  fileProcessingResult.structuredData.nextStage = 'document-categorization';
}

// Pass binary data forward for downstream processing
return [{
  json: fileProcessingResult,
  binary: binaryData
}];