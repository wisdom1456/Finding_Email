---

# Step 8: OpenAI Integration Architecture

## Executive Summary

This document provides a comprehensive architecture for replacing the simulated AI logic in the n8n workflow with live OpenAI GPT-4 integration. The implementation will transform two key nodes (`Extract Intake Form Data` and `Analyze Case Documents`) from hardcoded simulations to dynamic AI-powered processors while maintaining the existing workflow structure and data contracts.

## 1. AI Provider Selection: OpenAI

### OpenAI GPT-4 Advantages for Legal Document Processing

**Pros:**
- Industry-leading performance for structured data extraction
- Excellent JSON mode support for reliable output formatting
- Fast response times with GPT-4 Turbo
- Mature API with extensive documentation
- Native n8n integration support available
- Strong reasoning capabilities for legal analysis
- Consistent JSON formatting with proper prompting

**Model Selection:**
- **Intake Form Processing**: GPT-4 Turbo (balance of cost and performance)
- **Case Documents Analysis**: GPT-4 Turbo (sufficient for complex analysis)

**Cost Estimates:**
- Input: ~$0.01/1K tokens
- Output: ~$0.03/1K tokens
- Typical intake form: ~$0.005-0.015 per document
- Typical case analysis: ~$0.10-0.50 per document set

## 2. OpenAI Credential Management Strategy

### n8n Credential Configuration

#### Step 1: Create OpenAI API Credentials
1. Navigate to n8n Credentials section
2. Click "Add Credential"
3. Select "OpenAI" credential type
4. Configuration:
   - **Name**: `OpenAI-API-Legal-Workflow`
   - **API Key**: `{your-openai-api-key}`
   - **Organization ID**: `{your-org-id}` (optional)

#### Step 2: Environment-Specific Configuration
```json
{
  "production": {
    "credential": "OpenAI-API-Legal-Workflow",
    "apiEndpoint": "https://api.openai.com/v1/chat/completions"
  },
  "development": {
    "credential": "OpenAI-API-Legal-Workflow-Dev",
    "apiEndpoint": "https://api.openai.com/v1/chat/completions"
  }
}
```

#### Step 3: Security Best Practices
1. **API Key Storage**: Never hardcode API keys in workflow JSON
2. **Credential Rotation**: Implement quarterly key rotation
3. **Access Control**: Limit credential access to authorized workflows only
4. **Usage Monitoring**: Track API usage to avoid quota issues
5. **Rate Limit Management**: Implement proper request throttling

## 3. Node Implementation Guidelines

### Extract Intake Form Data Node Transformation

#### Current State (Simulated)
- Node ID: `ai-extract-intake-001-2025`
- Type: `n8n-nodes-base.code`
- Logic: Hardcoded JSON response

#### Target State (Live OpenAI)
Replace the existing code node with a sequence of three nodes:

**Node 1: Prepare OpenAI Request (Code Node)**
```javascript
// OpenAI Intake Form Request Preparation
const inputData = $input.first().json;
const binaryData = $input.first().binary || {};

// Validate input structure
if (!inputData || inputData.documentType !== "intakeForm") {
  throw new Error("Invalid input: Expected intakeForm document type");
}

// Extract binary data
const binaryKey = inputData.intakeFormData.binaryDataReference;
const documentBinary = binaryData[binaryKey];

if (!documentBinary) {
  throw new Error(`Binary data not found for key: ${binaryKey}`);
}

// Note: In production, implement actual text extraction from PDF/DOCX
// For now, assume text extraction happens upstream or use simulated text
const documentText = documentBinary.data ? documentBinary.data.toString('utf8') : `
LEGAL INTAKE FORM

Client Information:
Name: John Smith
Phone: (555) 123-4567
Email: john.smith@email.com
Address: 123 Main Street, City, ST 12345

Case Information:
Case Reference: CASE-2025-001
Matter Type: Personal Injury
Date of Incident: January 15, 2025
Brief Description: Motor vehicle accident at intersection of Main St and Oak Ave. Client was injured when defendant ran red light.

Attorney Information:
Assigned Attorney: Sarah Johnson, Esq.
Bar Number: 12345
Specialty: Personal Injury Law

Additional Notes:
Client reported back and neck pain. Medical treatment ongoing at City Hospital.
`;

// Prepare OpenAI request payload
const openaiRequestPayload = {
  model: "gpt-4-turbo",
  messages: [
    {
      role: "system",
      content: "You are an expert legal data extraction assistant. Extract information from legal intake forms and return valid JSON only."
    },
    {
      role: "user", 
      content: `Extract information from this intake form document and format as valid JSON.

Document content:
${documentText}

Extract according to this JSON schema:
{
  "clientInfo": {
    "clientName": "string",
    "contactInfo": "string"
  },
  "caseInfo": {
    "caseReference": "string", 
    "summary": "string"
  },
  "attorneyInfo": {
    "attorneyName": "string"
  }
}

Return ONLY the valid JSON object.`
    }
  ],
  response_format: { type: "json_object" },
  max_tokens: 1000,
  temperature: 0.1
};

return [{
  json: {
    ...inputData,
    openaiRequestPayload: openaiRequestPayload,
    processingMetadata: {
      nodeType: "openai-request-preparation",
      requestPreparedAt: new Date().toISOString(),
      documentTextLength: documentText.length
    }
  },
  binary: binaryData
}];
```

**Node 2: Execute OpenAI Request (HTTP Request Node)**
- **Method**: POST
- **URL**: `https://api.openai.com/v1/chat/completions`
- **Authentication**: Predefined Credential (OpenAI-API-Legal-Workflow)
- **Headers**:
  - `Content-Type`: `application/json`
  - `Authorization`: `Bearer {{$credentials.api_key}}` (handled by n8n credential)
- **Body**: `={{ JSON.stringify($json.openaiRequestPayload) }}`

**Node 3: Parse OpenAI Response (Code Node)**
```javascript
// Parse OpenAI Response and Validate
const openaiResponse = $input.first().json;
const originalData = $items("Prepare OpenAI Request")[0].json;

// Initialize processing result
const processingResult = {
  isValid: true,
  errors: [],
  extractedData: null,
  processingTimestamp: new Date().toISOString(),
  extractionMetadata: {
    nodeType: "openai-response-parser",
    processingBranch: "intake-analysis",
    aiModel: "gpt-4-turbo"
  }
};

try {
  // Check for API errors first
  if (openaiResponse.error) {
    throw new Error(`OpenAI API Error: ${openaiResponse.error.message || 'Unknown API error'}`);
  }
  
  // Extract OpenAI response content
  if (!openaiResponse.choices || !Array.isArray(openaiResponse.choices) || openaiResponse.choices.length === 0) {
    throw new Error("Invalid API response: Missing choices array");
  }
  
  const choice = openaiResponse.choices[0];
  if (!choice.message || !choice.message.content) {
    throw new Error("Invalid API response: Missing message content");
  }
  
  const aiContent = choice.message.content;
  
  // Parse JSON response
  let extractedData;
  try {
    extractedData = JSON.parse(aiContent);
  } catch (parseError) {
    throw new Error(`JSON parsing failed: ${parseError.message}`);
  }
  
  // Validate required fields
  const requiredFields = [
    'clientInfo.clientName',
    'caseInfo.caseReference', 
    'attorneyInfo.attorneyName'
  ];
  
  for (const field of requiredFields) {
    const fieldPath = field.split('.');
    let value = extractedData;
    for (const key of fieldPath) {
      value = value?.[key];
    }
    if (!value || typeof value !== 'string' || value.trim().length === 0) {
      throw new Error(`Missing or invalid required field: ${field}`);
    }
  }
  
  // Set successful extraction result
  processingResult.extractedData = extractedData;
  processingResult.extractionMetadata.fieldsExtracted = Object.keys(extractedData).length;
  processingResult.extractionMetadata.tokenUsage = openaiResponse.usage || {};
  processingResult.message = "Intake form data successfully extracted using OpenAI";
  
  // Preserve original routing data
  processingResult.originalRoutingData = {
    documentType: originalData.documentType,
    caseInfo: originalData.caseInfo,
    intakeFormData: originalData.intakeFormData,
    processingMetadata: originalData.processingMetadata
  };
  
} catch (error) {
  processingResult.isValid = false;
  processingResult.errors.push(`AI processing failed: ${error.message}`);
  processingResult.extractionMetadata.rawResponse = openaiResponse;
  
  // Implement fallback strategy
  console.error('OpenAI processing failed, using fallback', error.message);
  
  // Return simulated response structure as fallback
  processingResult.extractedData = {
    clientInfo: {
      clientName: "AI_PROCESSING_FAILED",
      contactInfo: "Please review manually"
    },
    caseInfo: {
      caseReference: `MANUAL_REVIEW_${new Date().toISOString().split('T')[0]}`,
      summary: "AI processing failed - manual review required"
    },
    attorneyInfo: {
      attorneyName: "REQUIRES_MANUAL_ENTRY"
    }
  };
  
  processingResult.isValid = true;
  processingResult.fallbackUsed = true;
  processingResult.message = "Fallback response used due to AI processing failure";
}

return [{
  json: processingResult,
  binary: $items("Prepare OpenAI Request")[0].binary
}];
```

### Analyze Case Documents Node Transformation

#### Current State (Simulated)
- Node ID: `analyze-case-docs-001-2025`
- Type: `n8n-nodes-base.code`
- Logic: Hardcoded JSON response

#### Target State (Live OpenAI)
Replace with similar three-node sequence:

**Node 1: Prepare Case Analysis Request (Code Node)**
```javascript
// OpenAI Case Documents Request Preparation
const inputData = $input.first().json;
const binaryData = $input.first().binary || {};

// Validate input data structure
if (!inputData || !inputData.isValid || !inputData.aggregatedDocumentsText) {
  throw new Error("Invalid input: Missing aggregated documents text");
}

const documentsText = inputData.aggregatedDocumentsText;

// Prepare OpenAI request payload
const openaiRequestPayload = {
  model: "gpt-4-turbo",
  messages: [
    {
      role: "system",
      content: "You are a specialized legal analysis AI. Analyze case documents and extract key legal information in structured JSON format."
    },
    {
      role: "user",
      content: `Analyze these case documents and extract key legal information.

Documents:
---
${documentsText}
---

Extract information according to this JSON schema:
{
  "keyEntities": {
    "plaintiffs": ["string"],
    "defendants": ["string"], 
    "judges": ["string"],
    "other_parties": ["string"]
  },
  "keyFacts": [
    {
      "fact": "string",
      "source_document": "string"
    }
  ],
  "timelineOfEvents": [
    {
      "date": "YYYY-MM-DD",
      "event": "string", 
      "source_document": "string"
    }
  ],
  "legalContext": {
    "statedClaims": ["string"],
    "defenses": ["string"]
  }
}

Return ONLY the valid JSON object.`
    }
  ],
  response_format: { type: "json_object" },
  max_tokens: 4000,
  temperature: 0.1
};

return [{
  json: {
    ...inputData,
    openaiRequestPayload: openaiRequestPayload,
    processingMetadata: {
      nodeType: "openai-case-analysis-preparation",
      requestPreparedAt: new Date().toISOString(),
      documentsTextLength: documentsText.length
    }
  },
  binary: binaryData
}];
```

**Node 2: Execute Case Analysis Request (HTTP Request Node)**
- Same configuration as intake form but with higher timeout (60s)
- **Body**: `={{ JSON.stringify($json.openaiRequestPayload) }}`

**Node 3: Parse Case Analysis Response (Code Node)**
```javascript
// Parse Case Analysis OpenAI Response
const openaiResponse = $input.first().json;
const originalData = $items("Prepare Case Analysis Request")[0].json;

// Initialize processing result
const processingResult = {
  isValid: true,
  errors: [],
  analysisData: null,
  processingTimestamp: new Date().toISOString(),
  analysisMetadata: {
    nodeType: "openai-case-analysis-parser",
    processingBranch: "case-documents-analysis",
    aiModel: "gpt-4-turbo"
  }
};

try {
  // Check for API errors first
  if (openaiResponse.error) {
    throw new Error(`OpenAI API Error: ${openaiResponse.error.message || 'Unknown API error'}`);
  }
  
  // Extract OpenAI response content
  if (!openaiResponse.choices || !Array.isArray(openaiResponse.choices) || openaiResponse.choices.length === 0) {
    throw new Error("Invalid API response: Missing choices array");
  }
  
  const choice = openaiResponse.choices[0];
  if (!choice.message || !choice.message.content) {
    throw new Error("Invalid API response: Missing message content");
  }
  
  const aiContent = choice.message.content;
  
  // Parse JSON response
  let analysisData;
  try {
    analysisData = JSON.parse(aiContent);
  } catch (parseError) {
    throw new Error(`JSON parsing failed: ${parseError.message}`);
  }
  
  // Validate required top-level fields
  const requiredFields = ['keyEntities', 'keyFacts', 'timelineOfEvents', 'legalContext'];
  for (const field of requiredFields) {
    if (!analysisData[field]) {
      throw new Error(`Missing required field: ${field}`);
    }
  }
  
  // Validate keyEntities structure
  if (!analysisData.keyEntities.plaintiffs || !Array.isArray(analysisData.keyEntities.plaintiffs)) {
    throw new Error("keyEntities.plaintiffs must be an array");
  }
  
  // Set successful analysis result
  processingResult.analysisData = analysisData;
  processingResult.analysisMetadata.entitiesExtracted = {
    plaintiffs: analysisData.keyEntities.plaintiffs.length,
    defendants: analysisData.keyEntities.defendants.length,
    judges: analysisData.keyEntities.judges.length,
    other_parties: analysisData.keyEntities.other_parties.length
  };
  processingResult.analysisMetadata.factsExtracted = analysisData.keyFacts.length;
  processingResult.analysisMetadata.timelineEventsExtracted = analysisData.timelineOfEvents.length;
  processingResult.analysisMetadata.tokenUsage = openaiResponse.usage || {};
  processingResult.message = "Case documents successfully analyzed using OpenAI";
  
  // Preserve original preparation data
  processingResult.originalPreparationData = {
    preparationResult: originalData,
    routingData: originalData.originalRoutingData || {}
  };
  
} catch (error) {
  processingResult.isValid = false;
  processingResult.errors.push(`AI analysis failed: ${error.message}`);
  processingResult.analysisMetadata.rawResponse = openaiResponse;
  
  // Implement fallback strategy for case documents
  console.error('OpenAI case analysis failed, using fallback', error.message);
  
  // Return simulated response structure as fallback
  processingResult.analysisData = {
    keyEntities: {
      plaintiffs: ["AI_PROCESSING_FAILED"],
      defendants: ["REQUIRES_MANUAL_REVIEW"],
      judges: ["UNKNOWN"],
      other_parties: ["MANUAL_ANALYSIS_NEEDED"]
    },
    keyFacts: [{
      fact: "AI processing failed - manual document review required",
      source_document: "System Error"
    }],
    timelineOfEvents: [{
      date: new Date().toISOString().split('T')[0],
      event: "AI analysis failure - manual processing required",
      source_document: "System Error"
    }],
    legalContext: {
      statedClaims: ["Manual review required due to AI processing failure"],
      defenses: ["Manual analysis needed"]
    }
  };
  
  processingResult.isValid = true;
  processingResult.fallbackUsed = true;
  processingResult.message = "Fallback case analysis used due to AI processing failure";
}

return [{
  json: processingResult,
  binary: $items("Prepare Case Analysis Request")[0].binary
}];
```

## 4. Error Handling and Resilience Strategy

### OpenAI-Specific Error Handling

#### Retry Configuration
```javascript
// Retry Configuration for HTTP Request Nodes
const retryConfig = {
  maxRetries: 3,
  retryDelayMs: 2000,
  exponentialBackoff: true,
  retryOn: [
    429, // Rate limit
    500, // Internal server error
    502, // Bad gateway
    503, // Service unavailable
    504  // Gateway timeout
  ]
};
```

#### OpenAI Error Response Processing
```javascript
// OpenAI Error Handler Node (Code Node)
const response = $input.first();

// Check for OpenAI-specific errors
if (response.json.error) {
  const error = response.json.error;
  
  // Handle different OpenAI error types
  switch (error.type) {
    case 'insufficient_quota':
      return [{
        json: {
          isValid: false,
          errors: ['OpenAI quota exceeded. Please check billing.'],
          errorType: 'quota_exceeded'
        }
      }];
      
    case 'rate_limit_exceeded':
      return [{
        json: {
          isValid: false,
          errors: ['OpenAI rate limit exceeded. Please try again later.'],
          retryAfter: 60,
          errorType: 'rate_limit'
        }
      }];
      
    case 'invalid_request_error':
      return [{
        json: {
          isValid: false,
          errors: [`Invalid request: ${error.message}`],
          errorType: 'invalid_request'
        }
      }];
      
    case 'server_error':
      return [{
        json: {
          isValid: false,
          errors: [`OpenAI server error: ${error.message}`],
          errorType: 'server_error',
          shouldRetry: true
        }
      }];
      
    default:
      return [{
        json: {
          isValid: false,
          errors: [`Unknown OpenAI error: ${error.message || 'Unexpected error occurred'}`],
          errorType: 'unknown'
        }
      }];
  }
}

// If no errors, pass through response
return [response];
```

## 5. Implementation Roadmap

### Phase 1: Intake Form Integration (Week 1)
1. Configure OpenAI credentials in n8n
2. Replace `Extract Intake Form Data` node with 3-node OpenAI sequence
3. Implement error handling and fallback logic
4. Test with sample intake forms

### Phase 2: Case Documents Integration (Week 2)  
1. Replace `Analyze Case Documents` node with 3-node OpenAI sequence
2. Implement case-specific error handling
3. Test with multiple document sets
4. Validate output schema compliance

### Phase 3: Monitoring & Optimization (Week 3)
1. Implement comprehensive logging and metrics
2. Set up alerting and monitoring dashboards
3. Performance testing and optimization
4. Circuit breaker implementation

### Phase 4: Production Deployment (Week 4)
1. Production credential setup
2. Staged rollout with traffic splitting
3. Performance monitoring and validation
4. Full production deployment

## 6. OpenAI-Specific Configuration

### API Endpoints
- **Primary**: `https://api.openai.com/v1/chat/completions`
- **Model Selection**: `gpt-4-turbo` for both intake and case analysis

### Timeout Settings
- **Intake Forms**: 30 seconds
- **Case Documents**: 60 seconds  
- **Retry Strategy**: 3 attempts with exponential backoff

### Cost Management
- **Token Tracking**: Monitor usage via OpenAI response metadata
- **Estimated Costs**:
  - Intake forms: ~$0.005-0.015 per document
  - Case analysis: ~$0.10-0.50 per document set
- **Rate Limits**: Respect OpenAI tier limits

---

**Next Steps**: This OpenAI-focused architecture provides the complete blueprint for integrating live GPT-4 models into the n8n workflow. The implementation should follow the phased approach outlined above, with careful testing and monitoring at each stage.