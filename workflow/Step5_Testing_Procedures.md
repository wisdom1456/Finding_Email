# Step 5: Document Categorization Testing Procedures

## Pre-Testing Setup

### 1. Workflow State Verification
Before testing Step 5, ensure:
- Step 4 (Extract Binary Files) is working correctly
- Current workflow has all nodes from Steps 1-4 properly connected
- Test files are available (Fefer case documents)

### 2. Add Step 5 Nodes to Workflow

#### Add Document Router Node
1. **Add Code Node** after "Extract Binary Files"
   - Name: `Categorize Documents`
   - Code: Copy from [`Step5_DocumentRouter_Code.js`](Step5_DocumentRouter_Code.js)
   - Connect input from "Extract Binary Files" node

#### Add IF Nodes for Routing
2. **Add First IF Node** after "Categorize Documents"
   - Name: `Route Intake Form`
   - Connect input from "Categorize Documents" node
   - Expression: `{{ $json.documentType === "intakeForm" }}`

3. **Add Second IF Node** after "Categorize Documents" (parallel connection)
   - Name: `Route Case Documents`
   - Connect input from "Categorize Documents" node
   - Expression: `{{ $json.documentType === "caseDocuments" }}`

#### Add Temporary Response Nodes
4. **Add Response Node for Intake Branch**
   - Name: `Intake Form Response`
   - Connect to "Route Intake Form" true output
   - Response Body: `{{ $json }}`

5. **Add Response Node for Case Documents Branch**
   - Name: `Case Documents Response`
   - Connect to "Route Case Documents" true output
   - Response Body: `{{ $json }}`

## Testing Scenarios

### Test 1: Standard Document Set
**Objective**: Verify basic branching functionality
**Input**: 1 intake form + 2 case documents

**Test Data**:
```bash
curl -X POST https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload \
  -F "clientName=Test Client" \
  -F "attorneyName=Test Attorney" \
  -F "intakeForm=@test-intake.pdf" \
  -F "caseDocument0=@test-document1.pdf" \
  -F "caseDocument1=@test-document2.pdf"
```

**Expected Results**:
- Two separate workflow branches execute
- Intake form branch receives: `documentType: "intakeForm"`
- Case documents branch receives: `documentType: "caseDocuments"`
- Each branch has appropriate file metadata
- Binary data preserved in each branch

**Validation Steps**:
1. Check n8n execution log shows 2 items from Document Router
2. Verify IF nodes route correctly to their respective true outputs
3. Confirm each response node receives expected data structure
4. Validate binary data references are correct

### Test 2: Large Document Set
**Objective**: Test performance with multiple case documents
**Input**: 1 intake form + 5 case documents

**Test Data**:
```bash
curl -X POST https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload \
  -F "clientName=Large Case Client" \
  -F "attorneyName=Test Attorney" \
  -F "intakeForm=@test-intake.pdf" \
  -F "caseDocument0=@doc1.pdf" \
  -F "caseDocument1=@doc2.pdf" \
  -F "caseDocument2=@doc3.pdf" \
  -F "caseDocument3=@doc4.pdf" \
  -F "caseDocument4=@doc5.pdf"
```

**Expected Results**:
- Case documents branch shows `documentCount: 5`
- All 5 documents listed in documents array
- Binary data includes all 5 case document references
- Total file size calculated correctly

### Test 3: Error Handling - Missing Intake Form
**Objective**: Verify error handling when intake form is missing
**Input**: 0 intake forms + 2 case documents

**Test Data**:
```bash
curl -X POST https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload \
  -F "clientName=Error Test Client" \
  -F "attorneyName=Test Attorney" \
  -F "caseDocument0=@test-document1.pdf" \
  -F "caseDocument1=@test-document2.pdf"
```

**Expected Results**:
- Document Router returns error response
- Error message: "Intake form is required but missing from file catalog"
- No branching occurs
- IF nodes do not execute

### Test 4: Error Handling - Missing Case Documents
**Objective**: Verify error handling when no case documents provided
**Input**: 1 intake form + 0 case documents

**Test Data**:
```bash
curl -X POST https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload \
  -F "clientName=Error Test Client" \
  -F "attorneyName=Test Attorney" \
  -F "intakeForm=@test-intake.pdf"
```

**Expected Results**:
- Document Router returns error response  
- Error message: "At least one case document is required but none found in file catalog"
- No branching occurs

### Test 5: Real Fefer Case Data
**Objective**: Test with actual case files
**Input**: Fefer intake form + 2 Fefer case documents

**Test Data**:
```bash
curl -X POST https://brflorida.app.n8n.cloud/webhook/legal-analysis-upload \
  -F "clientName=Yelena Gurevich" \
  -F "attorneyName=Lourdes Transki" \
  -F "intakeForm=@Fefer - Intake.pdf" \
  -F "caseDocument0=@document1.pdf" \
  -F "caseDocument1=@document2.pdf"
```

**Expected Results**:
- Realistic file sizes and metadata
- Proper case reference generation
- All real file names preserved

## Validation Checklist

### Document Router Validation
- [ ] Creates exactly 2 output items from 1 input
- [ ] First item has `documentType: "intakeForm"`
- [ ] Second item has `documentType: "caseDocuments"`
- [ ] Binary data split correctly between branches
- [ ] Case information preserved in both branches
- [ ] Processing metadata added correctly
- [ ] Error handling works for missing files

### IF Node Validation
- [ ] Routes intake form items through "Route Intake Form" IF node
- [ ] Routes case documents items through "Route Case Documents" IF node
- [ ] No items lost or misrouted
- [ ] Expressions evaluate correctly with 100% reliability
- [ ] Multiple items handled properly by each IF node

### Data Integrity Validation
- [ ] File metadata accurate in each branch
- [ ] Binary data references correct
- [ ] Case information identical in both branches
- [ ] File counts and sizes accurate
- [ ] Timestamps properly generated

### Error Handling Validation
- [ ] Missing intake form triggers appropriate error
- [ ] Missing case documents triggers appropriate error
- [ ] Invalid Step 4 data handled gracefully
- [ ] Error messages clear and actionable

## Debugging Common Issues

### Issue: IF Nodes Not Routing
**Symptoms**: Items not appearing in either branch
**Solutions**:
- Check IF node expressions for syntax errors
- Verify `documentType` field exists in data
- Test expressions in n8n expression editor
- Confirm IF nodes are connected to correct outputs

### Issue: Binary Data Missing
**Symptoms**: File references but no binary content
**Solutions**:
- Verify binary data passthrough from Step 4
- Check binary key names match references
- Confirm Document Router preserves binary data

### Issue: Only One Branch Executing
**Symptoms**: Only intake or case documents branch runs
**Solutions**:
- Check Document Router creates 2 output items
- Verify both IF node expressions are correct
- Ensure both IF nodes are connected to Document Router output
- Test with different document combinations

### Issue: Response Timeout
**Symptoms**: No response received from webhook
**Solutions**:
- Check if both response nodes are connected
- Verify n8n isn't waiting for both branches
- Consider adding Wait node if needed

## Performance Metrics

Track these metrics during testing:
- **Execution Time**: Document Router + Switch should be < 1 second
- **Memory Usage**: Monitor for large file sets
- **Success Rate**: Should be 100% for valid inputs
- **Error Rate**: Should catch all invalid scenarios

## Clean Up After Testing

After Step 5 validation:
1. Document findings in main findings document
2. Export successful workflow version
3. Remove temporary response nodes
4. Keep Document Router and IF nodes for Step 6 integration
5. Prepare for next step implementation

## Success Criteria Summary

✅ **Functional Requirements**:
- Documents correctly categorized into 2 branches
- All file metadata preserved and accurate
- Binary data properly split and referenced
- Error handling catches all invalid scenarios

✅ **Technical Requirements**:
- IF node routing works reliably with 100% success rate
- Data structures match specification
- Performance acceptable for expected loads
- Integration ready for subsequent steps

✅ **Quality Requirements**:
- No data loss during branching
- Consistent behavior across test scenarios
- Clear error messages for failures
- Maintainable code structure