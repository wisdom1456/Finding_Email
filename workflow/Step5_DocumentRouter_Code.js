// Step 5: Document Categorization Router
// This node creates separate processing branches for intake forms and case documents
// Based on the file catalog from Step 4, it prepares data for parallel processing

// Get the file processing result from Step 4
const step4Data = $input.first().json;
const binaryData = $input.first().binary || {};

// Initialize the routing results
const routingResults = {
  isValid: true,
  errors: [],
  branches: [],
  processingTimestamp: new Date().toISOString()
};

// Validate that we have the necessary data from Step 4
if (!step4Data || !step4Data.isValid) {
  routingResults.isValid = false;
  routingResults.errors.push("Invalid data received from Step 4 - file processing failed");
  return [{ json: routingResults }];
}

// Extract the structured data and file catalog
const structuredData = step4Data.structuredData || {};
const filesCatalog = structuredData.filesCatalog || step4Data.filesCatalog;

if (!filesCatalog) {
  routingResults.isValid = false;
  routingResults.errors.push("File catalog is missing from Step 4 data");
  return [{ json: routingResults }];
}

// Prepare output items for the Switch node
const outputItems = [];

// Branch 1: Intake Form Processing
if (filesCatalog.intakeForm) {
  const intakeFormBranch = {
    documentType: "intakeForm",
    caseInfo: structuredData.caseInfo || {},
    intakeFormData: {
      fileName: filesCatalog.intakeForm.fileName,
      fileSize: filesCatalog.intakeForm.fileSize,
      mimeType: filesCatalog.intakeForm.mimeType,
      uploadedAt: filesCatalog.intakeForm.uploadedAt,
      binaryDataReference: "intakeForm"
    },
    processingMetadata: {
      branch: "intake-analysis",
      documentCount: 1,
      processingStartedAt: new Date().toISOString(),
      priority: "high"
    },
    originalData: {
      step4Result: step4Data,
      totalFileCount: filesCatalog.fileCount,
      totalFileSize: filesCatalog.totalFileSize
    }
  };
  
  outputItems.push({
    json: intakeFormBranch,
    binary: { intakeForm: binaryData.intakeForm }
  });
  
  routingResults.branches.push("intake-analysis");
} else {
  routingResults.isValid = false;
  routingResults.errors.push("Intake form is required but missing from file catalog");
}

// Branch 2: Case Documents Processing
if (filesCatalog.caseDocuments && filesCatalog.caseDocuments.length > 0) {
  // Prepare binary data object for case documents
  const caseDocumentsBinary = {};
  
  // Add each case document to binary data
  filesCatalog.caseDocuments.forEach((doc, index) => {
    const binaryKey = `caseDocument${doc.index}`;
    if (binaryData[binaryKey]) {
      caseDocumentsBinary[binaryKey] = binaryData[binaryKey];
    }
  });
  
  const caseDocumentsBranch = {
    documentType: "caseDocuments",
    caseInfo: structuredData.caseInfo || {},
    caseDocumentsData: {
      documentCount: filesCatalog.caseDocuments.length,
      totalSize: filesCatalog.caseDocuments.reduce((total, doc) => total + doc.fileSize, 0),
      documents: filesCatalog.caseDocuments.map(doc => ({
        index: doc.index,
        fileName: doc.fileName,
        fileSize: doc.fileSize,
        mimeType: doc.mimeType,
        uploadedAt: doc.uploadedAt,
        binaryDataReference: `caseDocument${doc.index}`
      }))
    },
    processingMetadata: {
      branch: "case-documents-analysis",
      documentCount: filesCatalog.caseDocuments.length,
      processingStartedAt: new Date().toISOString(),
      priority: "normal"
    },
    originalData: {
      step4Result: step4Data,
      totalFileCount: filesCatalog.fileCount,
      totalFileSize: filesCatalog.totalFileSize
    }
  };
  
  outputItems.push({
    json: caseDocumentsBranch,
    binary: caseDocumentsBinary
  });
  
  routingResults.branches.push("case-documents-analysis");
} else {
  routingResults.isValid = false;
  routingResults.errors.push("At least one case document is required but none found in file catalog");
}

// If we have validation errors, return error response
if (routingResults.errors.length > 0) {
  routingResults.isValid = false;
  return [{ json: routingResults }];
}

// Update the processing status in structured data
const updatedStructuredData = {
  ...structuredData,
  dataProcessingStatus: {
    ...structuredData.dataProcessingStatus,
    documentsCategorized: true,
    categorizedAt: new Date().toISOString(),
    branchesCreated: routingResults.branches
  },
  nextStage: 'parallel-analysis'
};

// Add success metadata to the routing results
routingResults.message = `Successfully categorized ${filesCatalog.fileCount} documents into ${routingResults.branches.length} processing branches`;
routingResults.branchCount = routingResults.branches.length;
routingResults.structuredData = updatedStructuredData;

// Log the routing decision for debugging
console.log(`Document Categorization: Created ${outputItems.length} branches for processing`);
outputItems.forEach((item, index) => {
  console.log(`Branch ${index + 1}: ${item.json.documentType} (${item.json.processingMetadata.documentCount} documents)`);
});

// Return all output items for the Switch node
return outputItems;