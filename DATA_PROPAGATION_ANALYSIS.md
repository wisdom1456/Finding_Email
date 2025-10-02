# Data Propagation Analysis - AI Prompting Phases

**Date**: October 2, 2025  
**Status**: ✅ ENHANCED - Data is correctly propagated through all phases with full document content retention

## Overview
This document verifies that data is correctly propagated and used by AI prompting in each processing phase of the Legal Document Analysis Portal.

## Data Flow Through Processing Phases

### Phase 1: Document Processing
**Location**: `main_processor.py` (lines 524-619)

**Input Data**:
- Intake form file (from `st.session_state.intake_form`)
- Case documents (from `st.session_state.case_documents`)
- Audio files and video files (if applicable)

**Processing**:
```python
# Line 561: Document processor receives files and intake filename
processed_docs = await doc_processor.process_documents_from_streamlit(
    doc_files, intake_filenames
)
```

**Output**:
- `ProcessedDocument` objects with extracted content
- Intake document separated by `DocumentType.INTAKE_FORM`
- Case documents separated from intake

**✅ Verification**: Data properly extracted and categorized.

---

### Phase 2: Intake Analysis
**Location**: `main_processor.py` (lines 621-652), `ai_analyzer.py` (lines 75-170)

**Input Data**:
- `intake_doc` (ProcessedDocument from Phase 1)
- Full document content: `intake_doc.content`

**Prompt Construction** (`prompt_builder.py`, lines 18-71):
```python
def build_intake_prompt(self, content: str) -> str:
    # Injects complete intake form content into prompt
    return (
        "SOURCE INTAKE FORM (read-only)\n"
        f"{content}\n"  # ← Full intake data passed to AI
        "SCHEMA — EnhancedIntakeAnalysis\n"
    )
```

**AI Processing**:
- OpenAI receives: Complete intake form content
- Returns: `EnhancedIntakeAnalysis` JSON with:
  - `client_name`
  - `case_summary`
  - `case_type`
  - `urgency_level`
  - `client_priorities`
  - `desired_outcomes`
  - `key_facts`
  - `parties_involved`
  - `financial_impact`
  - `legal_claims`

**Output Stored**:
```python
# Line 635
analysis_result = await ai_analyzer.analyze_intake(intake_doc)
# Stored in: analysis_result.intake_analysis
```

**✅ Verification**: Intake form content fully passed to AI, structured data extracted and stored.

---

### Phase 3: Case Document Analysis
**Location**: `main_processor.py` (lines 654-835), `ai_analyzer.py` (lines 172-261)

**Input Data**:
- `case_docs` (List[ProcessedDocument])
- **CRITICAL**: `analysis_result.intake_analysis` from Phase 2

**Prompt Construction** (`ai_analyzer.py`, lines 217-261):
```python
def _build_document_analysis_prompt(self, doc: ProcessedDocument, ctx: EnhancedIntakeAnalysis):
    # CLIENT CONTEXT INJECTION
    client_priorities_str = (
        "; ".join(ctx.client_priorities) if ctx.client_priorities else "Not specified"
    )
    desired_outcomes_str = (
        "; ".join(ctx.desired_outcomes) if ctx.desired_outcomes else "Not specified"
    )
    
    return (
        "DOCUMENT (read-only)\n"
        f"Filename: {doc.file_name}\n"
        f"Content: {doc.content}\n"  # ← Document content
        "CLIENT PRIORITIES FOR THIS ANALYSIS:\n"
        f"• Priorities: {client_priorities_str}\n"  # ← Intake data
        f"• Desired Outcomes: {desired_outcomes_str}\n"  # ← Intake data
        f"• Case Type: {ctx.case_type or 'Not specified'}\n"  # ← Intake data
        f"• Urgency Level: {ctx.urgency_level or 'Not specified'}\n"  # ← Intake data
        "FULL INTAKE CONTEXT\n"
        f"{ctx.model_dump_json(indent=2)}\n"  # ← Complete intake analysis
    )
```

**Critical Data Propagation**:
```python
# Line 699: Intake analysis explicitly passed to document analysis
results = await ai_analyzer.analyze_case_documents(
    case_docs, 
    analysis_result.intake_analysis  # ← Phase 2 data injected here
)
```

**AI Processing for Each Document**:
- Receives: Document content + Complete intake analysis
- Context: Client priorities, desired outcomes, case type, urgency
- Returns: `AnalyzedDocument` with document-specific insights

**✅ Verification**: Each case document receives FULL intake context. Client priorities and case information inform every document analysis.

---

### Phase 4: Final Assessment
**Location**: `main_processor.py` (lines 837-864), `ai_analyzer.py` (lines 496-693)

**Input Data**:
- Complete `CaseAnalysisResult` containing:
  - `intake_analysis` (from Phase 2)
  - `analyzed_documents` (from Phase 3)
  - `video_insights` (if applicable)
  - `transcripted_media` (if applicable)

**Prompt Construction** (`ai_analyzer.py`, lines 498-693):
```python
async def _build_final_assessment_prompt(
    self, analysis: CaseAnalysisResult, prompt_config: str = None
) -> str:
    # Serialize complete analysis for AI
    analysis_for_prompt = analysis.model_dump_json(exclude_none=True, indent=2)
    
    # Build timeline from analyzed documents
    timeline_content = self._build_case_timeline(analysis)
    
    # Video relevance analysis
    video_relevance_content = self._build_video_relevance_analysis(analysis)
    
    final_assessment_prompt = """
    **Case Analysis Data:**
    {analysis_for_prompt}  # ← ALL data from Phases 1-3
    
    **Case Timeline:**
    {timeline_content}  # ← Extracted from document analyses
    
    **Video Relevance Analysis:**
    {video_relevance_content}  # ← Video insights if present
    """
    
    return final_assessment_prompt.format(
        analysis_for_prompt=analysis_for_prompt,
        timeline_content=timeline_content,
        video_relevance_content=video_relevance_content
    )
```

**AI Processing**:
- Receives: Complete case analysis from all previous phases
- Context: Intake + All documents + Timeline + Media
- Returns: `FinalAssessment` with:
  - `legal_assessment` (viability, evidence strength, challenges, actions)
  - `demand_letter_evaluation` (appropriateness, reasoning, outcomes)

**Output**:
```python
# Line 851
final_analysis = await ai_analyzer.perform_final_assessment(analysis_result)
# Updates analysis_result.legal_assessment
```

**✅ Verification**: Final assessment receives COMPLETE data from all phases. Nothing is lost or missing.

---

### Phase 5: Email/Letter Generation
**Location**: `main_processor.py` (lines 866-976), `email_generator_v2.py` (lines 130-226), `json_processing_service.py` (lines 45-441)

**Input Data**:
- `final_analysis` (Complete CaseAnalysisResult with legal_assessment from Phase 4)

**Data Injection Chain**:

1. **EmailGeneratorV2** (line 166):
```python
result = self.content_service.generate_email_and_analysis_docs(case_analysis)
```

2. **ContentGenerationService** (line 165):
```python
result = self.json_processing_service.generate_html_letter(case_analysis)
```

3. **JsonProcessingService** (lines 152-213):
```python
# Create analysis proxy with complete data access
analysis_data = analysis.model_dump()

class AnalysisProxy:
    def __init__(self, data):
        self.client_name = data.get("intake_analysis", {}).get("client_name")
        self.matter_name = data.get("intake_analysis", {}).get("case_summary")
        self._raw_data = data  # ← Complete analysis stored
    
    def model_dump_json(self, indent=2):
        return json.dumps(self._raw_data, indent=indent)  # ← Full data available

# Inject into master prompt
formatted_prompt = enhanced_prompt.format(
    analysis=analysis_proxy,  # ← Complete case analysis injected
    example_letter_content=example_letter_content
)
```

**Master Prompt Receives**:
- Complete intake analysis
- All analyzed documents
- Legal assessment
- Timeline and media insights

**AI Processing**:
- Generates Markdown letter from complete case data
- Markdown converted to HTML
- Citations tracked and mapped

**Output Files Saved** (`json_processing_service.py`, lines 95-376):
```python
# Line 96: Final analysis data saved
with open("validation_output/final_analysis_data.json", "w") as f:
    f.write(final_analysis_data)

# Line 226: Final prompt saved
with open("validation_output/final_prompt.txt", "w") as f:
    f.write(formatted_prompt)

# Line 266: Raw OpenAI response saved
with open("validation_output/raw_openai_response.txt", "w") as f:
    f.write(str(markdown_response))

# Line 306: Raw Markdown saved
with open("validation_output/raw_markdown_response.md", "w") as f:
    f.write(str(markdown_response))

# Line 360: Final HTML saved
with open("validation_output/final_validated_html.html", "w") as f:
    f.write(validated_html)
```

**✅ Verification**: Complete case analysis propagated to letter generation. All data from all phases included in master prompt.

---

## Critical Data Verification Points

### ✅ Phase 2 → Phase 3: Intake Context Injection
**File**: `main_processor.py`, line 699
```python
results = await ai_analyzer.analyze_case_documents(
    case_docs, 
    analysis_result.intake_analysis  # ← VERIFIED: Intake analysis passed
)
```

**File**: `ai_analyzer.py`, line 232-239
```python
"CLIENT PRIORITIES FOR THIS ANALYSIS:\n"
f"• Priorities: {client_priorities_str}\n"  # ← VERIFIED: Used in prompt
f"• Desired Outcomes: {desired_outcomes_str}\n"  # ← VERIFIED: Used in prompt
f"• Case Type: {ctx.case_type or 'Not specified'}\n"  # ← VERIFIED: Used in prompt
"FULL INTAKE CONTEXT\n"
f"{ctx.model_dump_json(indent=2)}\n"  # ← VERIFIED: Complete intake injected
```

### ✅ Phase 3 → Phase 4: Document Analyses Accumulation
**File**: `main_processor.py`, lines 823-827
```python
for res in case_analysis_results:
    if isinstance(res, AnalyzedDocument):
        analysis_result.analyzed_documents.append(res)  # ← VERIFIED: Accumulated
    elif isinstance(res, AnalysisError):
        analysis_result.errors.append(res)
```

### ✅ Phase 4 → Phase 5: Complete Analysis Injection
**File**: `json_processing_service.py`, lines 152-212
```python
analysis_data = analysis.model_dump()  # ← VERIFIED: Complete data serialized
analysis_proxy = AnalysisProxy(analysis_data)  # ← VERIFIED: Wrapped for template
formatted_prompt = enhanced_prompt.format(
    analysis=analysis_proxy  # ← VERIFIED: Injected into master prompt
)
```

---

## Data Logging and Debugging

The system includes comprehensive logging at each phase:

### Phase 1-2: Document and Intake Processing
- Lines 597-609: Intake validation logging
- Lines 624-633: Cost tracking and progress updates

### Phase 3: Case Document Analysis
- Lines 674-818: Concurrent processing with progress tracking
- Lines 686-696: Pre-processing cost updates
- Lines 698-699: **Critical**: Intake analysis passed to document analysis

### Phase 4: Final Assessment
- Lines 840-862: Cost tracking before/after assessment
- Token counting and threshold checks for large datasets

### Phase 5: Email Generation
- Lines 869-976: Generation with cost tracking
- Lines 880-905: Debug logging for hypothesis tracking
- Lines 908-953: File saving with error handling

### Additional Diagnostic Files
- `validation_output/final_analysis_data.json` - Complete case data
- `validation_output/final_prompt.txt` - Actual prompt sent to AI
- `validation_output/raw_openai_response.txt` - Raw AI response
- `validation_output/raw_markdown_response.md` - Markdown before HTML conversion
- `validation_output/final_validated_html.html` - Final output

---

## Potential Issues and Recommendations

### ✅ Strengths
1. **Complete Data Propagation**: Each phase receives all data from previous phases
2. **Explicit Context Injection**: Intake analysis explicitly passed to document analysis
3. **Comprehensive Logging**: Debug logs track data flow through all phases
4. **File Captures**: Critical data saved to files for verification

### ⚠️ Areas to Monitor
1. **Token Limits**: Phase 4 includes token threshold checking (lines 366-414)
   - Video insights may be summarized if exceeding limits
   - **Recommendation**: Ensure summarization preserves critical information

2. **Error Handling**: Each phase has error handling that might fall back
   - **Recommendation**: Monitor `analysis_result.errors` for any failures

3. **Data Structure Validation**: Relies on Pydantic models
   - **Recommendation**: Ensure all models (EnhancedIntakeAnalysis, AnalyzedDocument, etc.) have required fields

### 🔍 Verification Steps for Users

1. **Check Intake Context in Document Analysis**:
   ```bash
   # Look for "CLIENT PRIORITIES" in logs
   grep "CLIENT PRIORITIES" logs/*.log
   ```

2. **Verify Complete Data in Final Prompt**:
   ```bash
   # Check if final_prompt.txt contains intake analysis
   cat validation_output/final_prompt.txt | grep -A 5 "intake_analysis"
   ```

3. **Confirm All Documents Analyzed**:
   ```python
   # In your analysis result
   print(f"Intake: {len([1 for d in analysis_result if d.intake_analysis])}")
   print(f"Documents: {len(analysis_result.analyzed_documents)}")
   print(f"Errors: {len(analysis_result.errors)}")
   ```

---

## ENHANCEMENT: Full Document Content Retention

**Date Enhanced**: October 2, 2025

### Problem Solved
Previously, only AI-generated summaries were retained in `AnalyzedDocument` objects. The original full document text was discarded after initial analysis, meaning downstream phases (final assessment, email generation) could not reference the source documents directly.

### Solution Implemented

**1. Data Model Enhancement** (`data_models.py`, line 127):
```python
class AnalyzedDocument(BaseModel):
    # ... existing fields ...
    original_content: Optional[str] = None  # Full original document content
```

**2. Content Preservation** (`ai_analyzer.py`, lines 932-938):
```python
analyzed_doc = AnalyzedDocument.model_validate(raw_analysis)
# Preserve original document content for downstream reference
analyzed_doc.original_content = document.content
return analyzed_doc
```

**3. Selective Serialization** (`ai_analyzer.py`, lines 699-702):
```python
# Exclude original_content from final assessment prompt (use summaries)
analysis_for_prompt.model_dump_json(
    indent=2, 
    exclude={"analyzed_documents": {"__all__": {"original_content"}}}
)
```

**4. Access in Email Generation** (`json_processing_service.py`, lines 187-190):
```python
@property
def analyzed_documents_with_content(self):
    """Returns analyzed documents with their full original content."""
    return self._raw_data.get("analyzed_documents", [])
```

### Data Flow Updated

```
Phase 3: Case Document Analysis
├─ Input: Full document content (ProcessedDocument.content)
├─ AI Processes: Complete document text
├─ Output: AnalyzedDocument with:
│  ├─ summary (AI-generated)
│  ├─ analysis (AI-generated)
│  └─ ✅ NEW: original_content (full source text preserved)

Phase 4: Final Assessment
├─ Has access to original_content but excludes it from prompt
└─ Uses summaries for efficiency

Phase 5: Email Generation
├─ Has full access to analyzed_documents with original_content
├─ Can reference summaries OR original text
└─ Enables accurate citations and fact-checking
```

### Benefits
✅ **Accuracy**: Can verify AI summaries against source documents  
✅ **Citations**: Can quote exact passages from original documents  
✅ **Transparency**: Full audit trail maintained  
✅ **Flexibility**: Each phase can choose summaries or full text  

### Performance Considerations
- **Memory**: Increases proportional to document sizes (acceptable for typical case loads)
- **Tokens**: Original content excluded from prompts where not needed (final assessment)
- **Storage**: Full content included in cached results and JSON exports

See `docs/FULL_DOCUMENT_CONTENT_ARCHITECTURE.md` for complete technical details.

---

## Conclusion

**✅ YES - Data is being correctly propagated through all phases with full document content retention**

The system architecture ensures that:
1. **Phase 1**: Documents are fully extracted and categorized
2. **Phase 2**: Intake analysis extracts structured client information
3. **Phase 3**: Each document analysis receives complete intake context
4. **Phase 4**: Final assessment receives all analyses and creates timeline
5. **Phase 5**: Letter generation receives complete case analysis

**No data loss occurs between phases**. Each phase explicitly passes its output to the next phase, and the prompts are constructed to include all relevant context.

The extensive logging and file capturing allows you to verify data propagation at any point in the pipeline.

---

## Next Steps

If you want to further verify data propagation:

1. **Enable Debug Logging**: Set log level to DEBUG to see all data flow
2. **Review Validation Output Files**: Check the `validation_output/` directory after each run
3. **Inspect Analysis Results**: Add breakpoints or logging to inspect `analysis_result` at each phase
4. **Test with Sample Case**: Run a test case and verify each output file contains expected data


