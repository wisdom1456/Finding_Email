# Workflow-Build Plan: Intake Form to Findings Email

## Overview
This plan outlines the sequential construction of an n8n workflow that receives legal intake form data and generates a professional Findings email. Each step builds upon the previous one, allowing independent testing and validation at every stage.

## Phase 1: Foundation (Steps 1-3)
**Goal**: Establish basic data flow and validation

### Step 1: Webhook Trigger & Basic Response
**Nodes to add**:
- Webhook node (trigger)
- Respond to Webhook node (output)

**Functionality**: Receive HTTP POST request and send acknowledgment  
**Test data**: Simple JSON payload with clientName field  
**Pass criteria**: 
- Webhook receives data
- Returns 200 status with success message
- Data visible in n8n execution log

### Step 2: Data Structure Validation
**Nodes to add**:
- Code node (after webhook, before response)

**Functionality**: Validate required fields match Form_Output_Documentation.md schema  
**Test data**: Complete intake form JSON structure  
**Pass criteria**:
- Validates presence of clientName, attorneyName
- Returns error for missing required fields
- Passes valid data to response node

### Step 3: Intake Form Data Processing
**Nodes to add**:
- Set node (to structure intake data)

**Functionality**: Extract and organize intake form fields into standardized format  
**Test data**: Full intake form submission with all fields  
**Pass criteria**:
- All form fields correctly mapped
- Data structure matches expected schema
- Clean JSON output for next phase

## Phase 2: Document Handling (Steps 4-6)
**Goal**: Process uploaded documents

### Step 4: Binary Data Reception
**Nodes to add**:
- Function node (to handle multipart form data)

**Functionality**: Receive and catalog uploaded files  
**Test data**: Webhook call with one PDF file attached  
**Pass criteria**:
- File metadata extracted (name, size, type)
- Binary data accessible in workflow
- File count accurate

### Step 5: Document Categorization
**Nodes to add**:
- Switch node (to separate intake form from case documents)

**Functionality**: Route documents based on type/name  
**Test data**: Multiple files including intake form and case documents  
**Pass criteria**:
- Intake form identified correctly
- Case documents counted and listed
- Each document type routed to correct path

### Step 6: Document Information Extraction
**Nodes to add**:
- Function node (to create document summary)

**Functionality**: Extract document metadata without OCR  
**Test data**: Mix of PDF, DOCX, and TXT files  
**Pass criteria**:
- Document count accurate
- File types identified
- Summary JSON created with document list

## Phase 3: AI Analysis (Steps 7-9)
**Goal**: Add intelligent document analysis

### Step 7: Simple Text Analysis Setup
**Nodes to add**:
- HTTP Request node (configured for OpenAI API)
- Credentials setup

**Functionality**: Send test prompt to GPT-4o-mini  
**Test data**: Static test prompt about legal analysis  
**Pass criteria**:
- Successful API connection
- Response received from OpenAI
- No authentication errors

### Step 8: Intake Form Analysis
**Nodes to add**:
- Code node (to build analysis prompt)

**Functionality**: Analyze intake form data with AI  
**Test data**: Intake form data from Step 3  
**Pass criteria**:
- Extracts case type
- Identifies urgency level
- Returns structured analysis JSON

### Step 9: Document Analysis Loop
**Nodes to add**:
- Split in Batches node
- Loop nodes for document processing

**Functionality**: Analyze each document with AI  
**Test data**: 2-3 case documents  
**Pass criteria**:
- Each document analyzed individually
- Results aggregated correctly
- No loop errors

## Phase 4: Email Generation (Steps 10-12)
**Goal**: Create professional Findings email

### Step 10: Findings Template Creation
**Nodes to add**:
- Code node (to merge all analyses)

**Functionality**: Combine intake and document analyses  
**Test data**: Results from Steps 8 and 9  
**Pass criteria**:
- All data points included
- Coherent summary structure
- Ready for email formatting

### Step 11: Email Content Generation
**Nodes to add**:
- HTTP Request node (GPT-4o for email writing)

**Functionality**: Generate professional Findings letter  
**Test data**: Merged analysis from Step 10  
**Pass criteria**:
- Professional tone and format
- Includes all key findings
- Actionable recommendations

### Step 12: Final Response Assembly
**Nodes to add**:
- Code node (to create final response)

**Functionality**: Package email and metadata for front-end  
**Test data**: Generated email from Step 11  
**Pass criteria**:
- Response includes email content
- Metadata (doc count, analysis date) included
- Format matches front-end expectations

## Phase 5: Enhancement (Steps 13-15)
**Goal**: Add OCR and advanced features

### Step 13: OCR Integration
**Nodes to add**:
- HTTP Request nodes for Azure Document Intelligence
- Wait node for async processing

**Functionality**: Extract text from PDFs  
**Test data**: Scanned PDF document  
**Pass criteria**:
- Text extracted successfully
- OCR results integrated into analysis
- Error handling for OCR failures

### Step 14: Error Handling & Logging
**Nodes to add**:
- Error Trigger node
- Logging nodes

**Functionality**: Graceful error handling  
**Test data**: Various error scenarios  
**Pass criteria**:
- Errors caught and logged
- User-friendly error messages
- Workflow doesn't crash

### Step 15: Performance Optimization
**Nodes to add**:
- Parallel processing where applicable
- Cache nodes if needed

**Functionality**: Optimize for speed and reliability  
**Test data**: Large document set (10+ files)  
**Pass criteria**:
- Execution time under 2 minutes
- All documents processed
- Consistent results

## Testing Protocol for Each Step

### Before each step:
1. Create new workflow or duplicate existing
2. Import only the nodes for current step
3. Configure credentials if needed
4. Use exact test data specified

### During testing:
1. Execute workflow with test data
2. Check execution log for errors
3. Verify output matches pass criteria
4. Save successful workflow version

### After testing:
1. Document any issues encountered
2. Note actual vs expected output
3. Export workflow JSON
4. Proceed to next step only after current step passes

## Required Test Data Files

1. **minimal-test.json**: `{"clientName": "Test Client"}`
2. **complete-intake.json**: Full structure from Form_Output_Documentation.md
3. **test-intake.pdf**: Sample intake form PDF
4. **test-case-doc.pdf**: Sample case document
5. **test-bundle.zip**: Multiple test documents

## Important Notes

- **n8n Version**: Cloud version 1.102.3
- **Credentials**: Must be configured for OpenAI and Azure services
- **Webhook URL**: Will be generated by n8n for testing
- **Front-end Integration**: Can be modified as needed during build

This plan provides a clear, incremental path from the simplest possible webhook receiver to a full-featured document analysis and email generation system. Each step is independently testable and builds logically toward the complete solution.