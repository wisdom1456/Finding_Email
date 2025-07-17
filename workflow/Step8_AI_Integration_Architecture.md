---

# Step 8: AI Integration Architecture

## Executive Summary

This document provides a comprehensive architecture for replacing the simulated AI logic in the n8n workflow with live Large Language Model (LLM) integration. The implementation will transform two key nodes (`Extract Intake Form Data` and `Analyze Case Documents`) from hardcoded simulations to dynamic AI-powered processors while maintaining the existing workflow structure and data contracts.

## 1. AI Provider Selection

### Provider Analysis

#### OpenAI (GPT-4 Turbo / GPT-4o)
**Pros:**
- Industry-leading performance for structured data extraction
- Excellent JSON mode support for reliable output formatting
- Fast response times (especially GPT-4 Turbo)
- Mature API with extensive documentation
- Built-in n8n integration support

**Cons:**
- Higher cost compared to some alternatives
- 128K token limit may constrain large document sets
- Data privacy considerations for sensitive legal documents

**Cost:** ~$0.01/1K input tokens, $0.03/1K output tokens

#### Anthropic (Claude 3 Opus/Sonnet)
**Pros:**
- Superior performance on complex legal analysis
- 200K token context window (ideal for multiple documents)
- Strong reasoning capabilities for nuanced legal content
- Better handling of ambiguous or complex instructions
- Privacy-focused design

**Cons:**
- Higher cost for Opus model
- Slightly slower response times
- Less mature n8n integration (may require HTTP requests)

**Cost:** Opus ~$0.015/1K input, $0.075/1K output; Sonnet ~$0.003/1K input, $0.015/1K output

#### Google AI Platform (Gemini Pro)
**Pros:**
- Competitive pricing
- Good multilingual support
- 32K token context window
- Growing ecosystem integration

**Cons:**
- Less proven for legal document analysis
- Limited n8n native integration
- Newer platform with evolving capabilities

**Cost:** ~$0.00025/1K characters input, $0.0005/1K characters output

### Recommendation

**Primary Recommendation: Anthropic Claude 3**
- **Intake Form Processing**: Claude 3 Sonnet (balance of cost and performance)
- **Case Documents Analysis**: Claude 3 Opus (superior analysis capabilities)

**Rationale:**
1. Legal documents require nuanced understanding and careful analysis
2. Claude's larger context window (200K tokens) handles multiple documents effectively
3. Strong performance on structured output generation
4. Better privacy stance for sensitive legal data
5. Consistent JSON formatting with proper prompting

**Alternative Option: OpenAI GPT-4 Turbo**
- Use if n8n native integration is critical
- Suitable for both branches with JSON mode enabled
- More cost-effective for high-volume processing

## 2. Credential Management Strategy

### n8n Credential Configuration

#### Step 1: Create API Credentials
1. Navigate to n8n Credentials section
2. Click "Add Credential"
3. For Anthropic:
   - Search for "HTTP Request" credentials (custom implementation)
   - Name: "Anthropic-API-Legal-Workflow"
   - Add header authentication:
     - Header Name: `x-api-key`
     - Header Value: `{your-anthropic-api-key}`
   - Add second header:
     - Header Name: `anthropic-version`
     - Header Value: `2023-06-01`

4. For OpenAI (if using as alternative):
   - Select "OpenAI" credential type
   - Name: "OpenAI-API-Legal-Workflow"
   - API Key: `{your-openai-api-key}`

#### Step 2: Environment-Specific Configuration
```json
{
  "production": {
    "credential": "Anthropic-API-Legal-Workflow",
    "apiEndpoint": "https://api.anthropic.com/v1/messages"
  },
  "development": {
    "credential": "Anthropic-API-Legal-Workflow-Dev",
    "apiEndpoint": "https://api.anthropic.com/v1/messages"
  }
}
```

#### Step 3: Security Best Practices
1. **API Key Storage**: Never hardcode API keys in workflow JSON
2. **Credential Rotation**: Implement quarterly key rotation
3. **Access Control**: Limit credential access to authorized workflows only
4. **Audit Logging**: Enable n8n audit logs for credential usage
5. **Rate Limit Monitoring**: Track API usage to avoid quota issues

## 3. Node Implementation Guidelines

### Extract Intake Form Data Node Transformation

#### Current State (Simulated)
- Node ID: `ai-extract-intake-001-2025`
- Type: `n8n-nodes-base.code`
- Logic: Hardcoded JSON response

#### Target State (Live AI)
Replace the existing code node with a sequence of three nodes:

**Node 1: Prepare AI Request (Code Node)**
```javascript
// AI Intake Form Request Preparation
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
// For now, assume text extraction happens upstream
const documentText = documentBinary.data.toString('utf8');

// Prepare AI request payload
const aiRequestPayload = {
  model: "claude-3-sonnet-20240229",
  max_tokens: 1000,
  temperature: 0.1,
  messages: [{
    role: "user",
    content: `You are an expert legal data extraction assistant. Your task is to extract information from the provided intake form document and format it as a valid JSON object.

The document content is as follows:
${documentText}

Please extract the following information and structure it according to the JSON schema provided below. Ensure all fields are correctly populated and that the JSON is perfectly formatted.

**JSON Schema:**
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
  }]
};

return [{
  json: {
    ...inputData,
    aiRequestPayload: aiRequestPayload,
    processingMetadata: {
      nodeType: "ai-request-preparation",
      requestPreparedAt: new Date().toISOString()
    }
  },
  binary: binaryData
}];
```

**Node 2: Execute AI Request (HTTP Request Node)**
- **Method**: POST
- **URL**: `https://api.anthropic.com/v1/messages`
- **Authentication**: Predefined Credential (Anthropic-API-Legal-Workflow)
- **Headers**:
  - `Content-Type`: `application/json`
  - `anthropic-version`: `2023-06-01`
- **Body**: `={{ $json.aiRequestPayload }}`

**Node 3: Parse AI Response (Code Node)**
```javascript
// Parse AI Response and Validate
const aiResponse = $input.first().json;
const originalData = $items("Prepare AI Request")[0].json;

// Initialize processing result
const processingResult = {
  isValid: true,
  errors: [],
  extractedData: null,
  processingTimestamp: new Date().toISOString(),
  extractionMetadata: {
    nodeType: "ai-response-parser",
    processingBranch: "intake-analysis",
    aiModel: "claude-3-sonnet"
  }
};

try {
  // Extract AI response content
  const aiContent = aiResponse.content[0].text;
  
  // Parse JSON response
  const extractedData = JSON.parse(aiContent);
  
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
  processingResult.message = "Intake form data successfully extracted using live AI";
  
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
  processingResult.extractionMetadata.rawResponse = aiResponse;
}

return [{
  json: processingResult,
  binary: $items("Prepare AI Request")[0].binary
}];
```

### Analyze Case Documents Node Transformation

#### Current State (Simulated)
- Node ID: `analyze-case-docs-001-2025`
- Type: `n8n-nodes-base.code`
- Logic: Hardcoded JSON response

#### Target State (Live AI)
Replace with similar three-node sequence:

**Node 1: Prepare Case Analysis Request (Code Node)**
```javascript
// AI Case Documents Request Preparation
const inputData = $input.first().json;
const binaryData = $input.first().binary || {};

// Validate input structure
if (!inputData || !inputData.isValid || !inputData.aggregatedDocumentsText) {
  throw new Error("Invalid input: Missing aggregated documents text");
}

const documentsText = inputData.aggregatedDocumentsText;

// Prepare AI request payload
const aiRequestPayload = {
  model: "claude-3-opus-20240229", // Use Opus for complex analysis
  max_tokens: 4000,
  temperature: 0.1,
  messages: [{
    role: "user",
    content: `You are a specialized legal analysis AI. You will be given a collection of case documents. Your task is to perform a comprehensive analysis across all provided documents and extract key legal information.

The documents are provided below:
---
${documentsText}
---

Analyze the documents collectively and extract the following information. Structure your response as a single, valid JSON object according to the schema below.

**JSON Schema:**
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
  }]
};

return [{
  json: {
    ...inputData,
    aiRequestPayload: aiRequestPayload,
    processingMetadata: {
      nodeType: "ai-case-analysis-preparation",
      requestPreparedAt: new Date().toISOString(),
      documentsTextLength: documentsText.length
    }
  },
  binary: binaryData
}];
```

**Node 2: Execute Case Analysis Request (HTTP Request Node)**
- Same configuration as intake form but with higher timeout (60s)
- **Body**: `={{ $json.aiRequestPayload }}`

**Node 3: Parse Case Analysis Response (Code Node)**
```javascript
// Parse Case Analysis AI Response
const aiResponse = $input.first().json;
const originalData = $items("Prepare Case Analysis Request")[0].json;

// Initialize processing result
const processingResult = {
  isValid: true,
  errors: [],
  analysisData: null,
  processingTimestamp: new Date().toISOString(),
  analysisMetadata: {
    nodeType: "ai-case-analysis-parser",
    processingBranch: "case-documents-analysis",
    aiModel: "claude-3-opus"
  }
};

try {
  // Extract AI response content
  const aiContent = aiResponse.content[0].text;
  
  // Parse JSON response
  const analysisData = JSON.parse(aiContent);
  
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
  processingResult.message = "Case documents successfully analyzed using live AI";
  
  // Preserve original preparation data
  processingResult.originalPreparationData = {
    preparationResult: originalData,
    routingData: originalData.originalRoutingData || {}
  };
  
} catch (error) {
  processingResult.isValid = false;
  processingResult.errors.push(`AI analysis failed: ${error.message}`);
  processingResult.analysisMetadata.rawResponse = aiResponse;
}

return [{
  json: processingResult,
  binary: $items("Prepare Case Analysis Request")[0].binary
}];
```

## 4. Error Handling and Resilience Strategy

### API Error Handling

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

#### Error Response Processing
```javascript
// Error Handler Node (Code Node)
const response = $input.first();

// Check for HTTP errors
if (response.json.error) {
  const error = response.json.error;
  
  // Handle different error types
  switch (error.type) {
    case 'rate_limit_error':
      return [{
        json: {
          isValid: false,
          errors: ['Rate limit exceeded. Please try again later.'],
          retryAfter: error.details?.retry_after || 60,
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
      
    case 'api_error':
      return [{
        json: {
          isValid: false,
          errors: [`API error: ${error.message}`],
          errorType: 'api_error',
          shouldRetry: true
        }
      }];
      
    default:
      return [{
        json: {
          isValid: false,
          errors: [`Unknown error: ${error.message || 'Unexpected error occurred'}`],
          errorType: 'unknown'
        }
      }];
  }
}

// If no errors, pass through response
return [response];
```

### Fallback Strategies

#### 1. Graceful Degradation
```javascript
// Fallback to Simulated Response
if (processingResult.errors.length > 0) {
  // Log error for monitoring
  console.error('AI processing failed, using fallback', processingResult.errors);
  
  // Return simulated response structure
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
```

#### 2. Circuit Breaker Pattern
```javascript
// Circuit Breaker Implementation
const circuitBreaker = {
  failureThreshold: 5,
  recoveryTimeMs: 300000, // 5 minutes
  state: 'CLOSED' // CLOSED, OPEN, HALF_OPEN
};

// Check circuit breaker state before AI request
if (circuitBreaker.state === 'OPEN') {
  const timeSinceLastFailure = Date.now() - circuitBreaker.lastFailureTime;
  if (timeSinceLastFailure < circuitBreaker.recoveryTimeMs) {
    // Use fallback immediately
    return [{ json: getFallbackResponse() }];
  } else {
    // Try half-open state
    circuitBreaker.state = 'HALF_OPEN';
  }
}
```

### Monitoring and Alerting

#### Performance Metrics
```javascript
// Metrics Collection
const metrics = {
  timestamp: new Date().toISOString(),
  nodeId: 'ai-extract-intake-001-2025',
  requestDurationMs: responseTime,
  tokenUsage: {
    input: aiResponse.usage?.input_tokens || 0,
    output: aiResponse.usage?.output_tokens || 0,
    total: aiResponse.usage?.total_tokens || 0
  },
  success: processingResult.isValid,
  errorType: processingResult.isValid ? null : processingResult.errors[0],
  fallbackUsed: processingResult.fallbackUsed || false
};

// Send to monitoring system (webhook or logging service)
```

#### Alert Conditions
1. **Error Rate > 10%**: Alert operations team
2. **Response Time > 30s**: Performance degradation warning
3. **Token Usage > 90% of daily limit**: Cost management alert
4. **Circuit Breaker Open**: Service degradation alert

## 5. Implementation Roadmap

### Phase 1: Intake Form Integration (Week 1)
1. Configure Anthropic credentials in n8n
2. Replace `Extract Intake Form Data` node with 3-node AI sequence
3. Implement error handling and fallback logic
4. Test with sample intake forms

### Phase 2: Case Documents Integration (Week 2)
1. Replace `Analyze Case Documents` node with 3-node AI sequence
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

## 6. Testing Strategy

### Unit Testing
- Test each AI processing node independently
- Validate error handling scenarios
- Test fallback mechanisms

### Integration Testing
- End-to-end workflow testing
- Multiple document type validation
- Performance and load testing

### Production Validation
- A/B testing with simulated vs live AI
- Quality assurance comparing outputs
- Gradual traffic increase

---

**Next Steps**: This architecture document provides the complete blueprint for integrating live AI models into the n8n workflow. The implementation should follow the phased approach outlined above, with careful testing and monitoring at each stage.