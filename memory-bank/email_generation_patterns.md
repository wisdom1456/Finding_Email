# Email Generation Patterns

This document outlines the key patterns and best practices for generating high-quality, professional, and case-specific findings letters.

## 1. AI Analyzer Prompt Engineering

### **Critical Bug Fix: F-String Formatting**
A critical bug was identified and fixed where f-string prompts were using double curly braces (`{{content}}`) instead of single braces (`{content}`). This caused the AI to receive literal placeholder text instead of the actual document content, resulting in generic, non-specific analysis.

- **Incorrect**: `f"Analyze this: {{content}}"`
- **Correct**: `f"Analyze this: {content}"`

### **Timeline Event Generation**
To ensure accurate and descriptive timeline events, the following prompt enhancements were successful:

- **CRITICAL Instruction**: Explicitly mark the instruction as "CRITICAL" to emphasize its importance.
- **Descriptive Event Requirement**: Mandate that the `event` field contains a descriptive action or occurrence from the document content (15-30 words).
- **Prohibit Generic Placeholders**: Explicitly forbid the use of "N/A", "Not specified", or other generic placeholders.
- **Provide a Concrete Example**: Include a well-formed example of a timeline event object: `{"date": "2024-03-15", "event": "Property inspection revealed water damage..."}`.
- **Handle Empty Cases**: Instruct the AI to return an empty array `[]` if no timeline events are found.

### **Intake-Driven Analysis**
To make the analysis more relevant to the client's needs, the following prompt strategies were effective:

- **Highlight Client Priorities**: Explicitly include the client's priorities, desired outcomes, case type, and urgency level at the top of the prompt.
- **Emphasize Content Connection**: Instruct the AI to emphasize document content that directly supports or challenges the client's priorities.
- **Contextualize Evidence Strength**: Define `evidence_strength` based on how well the document supports the client's case.
- **Explicitly Link to Intake**: Require the `relevance_to_intake` field to explicitly connect the document to the client's stated priorities and desired outcomes.

## 2. Email Generator Prompt Engineering

### **Client-Friendly Narrative**
To transform the output from a technical memo to a polished, client-facing letter, the following prompt refinements were successful:

- **Tone and Language**: Instruct the AI to use a professional, confident, and client-focused tone, avoiding legal jargon where possible.
- **Narrative Structure**: Request a narrative structure with clear headings like **Our Analysis**, **Strengths of Your Case**, and **Potential Challenges**, instead of a list of bullet points.
- **Simple Explanations**: Ask for complex legal concepts to be explained in simple, professional language that a non-lawyer can easily understand.
- **Actionable Recommendations**: For strategic recommendations, instruct the AI to use a numbered list with clear, imperative language.

## 3. Quality Validation

A `QualityValidator` service was implemented to programmatically assess the quality of the generated findings letter.

- **Service Location**: [`backend/services/quality_validator.py`](backend/services/quality_validator.py)
- **Data Model**: The `QualityScore` data model is defined in [`backend/utils/data_models.py`](backend/utils/data_models.py).

### **Validation Checks**
The validator implements the following checks, each returning a score from 0.0 to 1.0:

- **`_check_professional_tone`**: Uses regex to check for common filler words and unprofessional punctuation. A lenient approach allows for a small number of minor infractions before penalizing the score.
- **`_check_completeness`**: Verifies that all essential sections of the letter (e.g., client name, summary, attorney name) are present.
- **`_check_clarity`**: Uses average sentence length as a simple proxy for clarity, penalizing overly long and complex sentences.
- **`_check_case_specificity`**: Scans for generic, non-specific phrases to ensure the letter is tailored to the case.

### **Integration**
The `QualityValidator` is integrated into the `EmailGenerator`'s `generate_email_and_analysis_docs` method. The resulting `quality_score` is included in the final `EmailResponse` object.

## 4. Rate Limiting and Token Management Patterns

### **Production-Ready Rate Limiting**
Critical patterns discovered during comprehensive testing for handling OpenAI API rate limits (30,000 tokens per minute):

#### **Sequential Processing Pattern**
```python
# Sequential document processing with delays
for i, doc_analysis in enumerate(analysis_docs):
    logger.info(f"Processing document {i+1}/{len(analysis_docs)}: {doc_analysis.filename}")
    
    # Generate email content with rate limiting
    result = await self._process_single_document(doc_analysis)
    
    # Rate limiting delay between documents
    if i < len(analysis_docs) - 1:  # Don't delay after last document
        await asyncio.sleep(3)  # 3-second delay prevents rate limit violations
```

#### **Token Estimation Algorithm**
```python
def estimate_tokens(text: str) -> int:
    """Estimate token count using 4 characters ≈ 1 token rule"""
    return len(text) // 4

# Usage in email generation
estimated_tokens = estimate_tokens(combined_content)
if estimated_tokens > 25000:  # Leave buffer for OpenAI limit
    content = truncate_content(combined_content, max_tokens=25000)
```

### **Content Truncation Strategy**
For documents exceeding token limits, implement intelligent truncation:

```python
def truncate_content(content: str, max_tokens: int = 25000) -> str:
    """Truncate content while preserving beginning and end context"""
    max_chars = max_tokens * 4  # Convert tokens to characters
    
    if len(content) <= max_chars:
        return content
    
    # Keep 80% from start, 20% from end
    start_chars = int(max_chars * 0.8)
    end_chars = int(max_chars * 0.2)
    
    start_content = content[:start_chars]
    end_content = content[-end_chars:]
    
    return f"{start_content}\n\n[CONTENT TRUNCATED]\n\n{end_content}"
```

### **Dynamic Model Selection**
Optimize cost and performance based on document complexity:

```python
def select_model_for_generation(estimated_tokens: int) -> str:
    """Select appropriate model based on content size"""
    if estimated_tokens > 20000:
        return "gpt-4o"  # Premium model for complex cases
    else:
        return "gpt-4o-mini"  # Cost-effective model for simpler cases
```

### **Progress Logging Pattern**
Provide clear feedback during long-running email generation:

```python
async def generate_email_with_progress(self, analysis_docs: List[DocumentAnalysis]) -> EmailResponse:
    """Generate email with comprehensive progress logging"""
    total_docs = len(analysis_docs)
    
    logger.info(f"Starting email generation for {total_docs} documents")
    
    for i, doc_analysis in enumerate(analysis_docs):
        # Log progress with percentage
        progress = ((i + 1) / total_docs) * 100
        logger.info(f"Progress: {progress:.1f}% - Processing {doc_analysis.filename}")
        
        # Process document with detailed logging
        start_time = time.time()
        result = await self._process_document(doc_analysis)
        elapsed = time.time() - start_time
        
        logger.info(f"Completed {doc_analysis.filename} in {elapsed:.2f}s")
```

### **Error Handling and Resilience**
Robust error handling patterns for production email generation:

```python
async def generate_with_retry(self, prompt: str, max_retries: int = 3) -> str:
    """Generate email content with retry logic"""
    for attempt in range(max_retries):
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                timeout=None  # Allow unlimited time for large documents
            )
            return response.choices[0].message.content
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

### **Large Document Set Optimization**
Patterns for handling complex cases with 40+ documents:

```python
async def optimize_for_large_sets(self, documents: List[DocumentAnalysis]) -> EmailResponse:
    """Optimized processing for large document sets"""
    
    # Sort documents by size for optimal processing order
    sorted_docs = sorted(documents, key=lambda d: len(d.content))
    
    # Process in batches with progress tracking
    batch_size = 10
    total_batches = len(sorted_docs) // batch_size + 1
    
    logger.info(f"Processing {len(sorted_docs)} documents in {total_batches} batches")
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(sorted_docs))
        batch = sorted_docs[start_idx:end_idx]
        
        logger.info(f"Processing batch {batch_num + 1}/{total_batches}")
        
        # Process batch with rate limiting
        for doc in batch:
            await self._process_document(doc)
            await asyncio.sleep(3)  # Rate limiting delay
```

### **Production Deployment Considerations**
Key patterns for production email generation:

1. **Timeout Configuration**: Use `timeout=None` for unlimited processing time
2. **Resource Monitoring**: Log token usage and processing times
3. **User Feedback**: Provide real-time progress updates for long operations
4. **Graceful Degradation**: Handle individual document failures without stopping entire process
5. **Quality Assurance**: Validate generated emails before delivery

These patterns ensure reliable, scalable email generation capable of handling complex legal document sets while maintaining API compliance and user experience standards.