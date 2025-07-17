// Bug Fix for Step 4: File Size Calculation
// Replace the file size calculation section in the Extract Binary Files node

// REPLACE THIS SECTION (around lines 45-50 and 70-75):
// totalSize += intakeFile.fileSize;
// totalSize += docFile.fileSize;

// WITH THIS CORRECTED VERSION:

// For intake form processing:
if (binaryData.intakeForm) {
  const intakeFile = binaryData.intakeForm;
  
  // Validate file type
  if (!allowedMimeTypes.includes(intakeFile.mimeType)) {
    fileProcessingResult.errors.push(`Intake form has invalid file type: ${intakeFile.mimeType}`);
  }
  
  // Extract metadata
  fileProcessingResult.filesCatalog.intakeForm = {
    fileName: intakeFile.fileName,
    fileSize: intakeFile.fileSize, // Keep original for display
    mimeType: intakeFile.mimeType,
    uploadedAt: new Date().toISOString()
  };
  
  // Convert fileSize to number for calculation
  const sizeInBytes = typeof intakeFile.fileSize === 'number' 
    ? intakeFile.fileSize 
    : intakeFile.data ? intakeFile.data.length : 0;
  totalSize += sizeInBytes;
  fileProcessingResult.filesCatalog.fileCount++;
}

// For case documents processing (in the while loop):
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
    fileSize: docFile.fileSize, // Keep original for display
    mimeType: docFile.mimeType,
    uploadedAt: new Date().toISOString()
  });
  
  // Convert fileSize to number for calculation
  const sizeInBytes = typeof docFile.fileSize === 'number' 
    ? docFile.fileSize 
    : docFile.data ? docFile.data.length : 0;
  totalSize += sizeInBytes;
  fileProcessingResult.filesCatalog.fileCount++;
  documentIndex++;
}

// The totalFileSize assignment remains the same:
fileProcessingResult.filesCatalog.totalFileSize = totalSize;