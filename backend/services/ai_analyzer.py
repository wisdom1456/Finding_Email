import json
import asyncio
from typing import Dict, Any, List
from fastapi import UploadFile, HTTPException
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
from openai import RateLimitError, APIError, APITimeoutError, OpenAI
from utils.data_models import IntakeAnalysis, CaseAnalysis, ProcessedDocument
from utils.validators import validate_intake_analysis, validate_case_analysis
from services.document_processor import DocumentProcessor

class AIAnalyzer:
    """
    Handles all interactions with the OpenAI API for document analysis.
    """
    def __init__(self, client: OpenAI):
        """
        Initializes the AIAnalyzer with the OpenAI client.
        """
        self.client = client
        self.doc_processor = DocumentProcessor()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError)),
    )
    async def _make_openai_request(self, prompt: str, model: str) -> Dict[str, Any]:
        """
        Makes a request to the OpenAI API with robust retry logic.
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except (RateLimitError, APIError, APITimeoutError) as e:
            print(f"AI ANALYZER: OpenAI API Error: {e}. Retrying...")
            raise
        except Exception as e:
            print(f"AI ANALYZER: An unexpected error occurred while calling OpenAI API: {type(e).__name__} - {e}")
            raise

    def _build_intake_prompt(self, document_content: str) -> str:
        """
        Builds the prompt for analyzing an intake form.
        """
        return f"""
        Analyze the following intake form and extract the information based on the JSON schema provided below.

        **Document Content:**
        ---
        {document_content}
        ---

        **JSON Schema:**
        {{
            "client_name": "string (full name)",
            "attorney_name": "string (full name)",
            "case_summary": "string (a brief summary of the case)",
            "key_facts": ["string"]
        }}
        """

    def _build_case_document_prompt(self, document: ProcessedDocument) -> str:
        """
        Builds the prompt for analyzing a case document.
        """
        return f"""
        Analyze the following case document, titled '{document.file_name}', and extract the information based on the JSON schema provided below.

        **Document Content:**
        ---
        {document.content}
        ---

        **JSON Schema:**
        {{
            "document_title": "string",
            "document_type": "string (e.g., 'Lease Agreement', 'Email Correspondence')",
            "key_entities": ["string"],
            "summary": "string",
            "timeline_events": [{{ "date": "string", "description": "string" }}]
        }}
        """

    async def analyze_intake(self, intake_form: UploadFile) -> IntakeAnalysis:
        """
        Analyzes an intake form and returns a structured analysis.
        """
        processed_intake = await self.doc_processor.process_documents([intake_form])
        if not processed_intake:
            raise HTTPException(status_code=400, detail="Could not process intake form.")
        
        return await self._analyze_single_intake_document(processed_intake[0])

    async def _analyze_single_intake_document(self, document: ProcessedDocument) -> IntakeAnalysis:
        """
        Helper function to analyze a single intake document.
        """
        prompt = self._build_intake_prompt(document.content)
        try:
            raw_analysis = await self._make_openai_request(prompt, model="gpt-4o-mini")
            return validate_intake_analysis(raw_analysis)
        except Exception as e:
            print(f"AI ANALYZER: Failed to process intake form '{document.file_name}': {type(e).__name__} - {e}")
            raise HTTPException(status_code=500, detail=f"Failed to analyze intake form due to an internal error.")

    async def _analyze_single_case_document(self, document: ProcessedDocument) -> CaseAnalysis:
        """
        Helper function to analyze a single case document.
        """
        prompt = self._build_case_document_prompt(document)
        try:
            raw_analysis = await self._make_openai_request(prompt, model="gpt-4o")
            return validate_case_analysis(raw_analysis)
        except Exception as e:
            print(f"AI ANALYZER: Failed to process case document '{document.file_name}': {type(e).__name__} - {e}")
            # Instead of returning a default object, re-raise as HTTPException
            raise HTTPException(status_code=500, detail=f"Failed to analyze document '{document.file_name}' due to an internal error.")

    async def analyze_case_documents(self, documents: List[ProcessedDocument]) -> List[CaseAnalysis]:
        """
        Analyzes multiple case documents in parallel using asyncio.gather.
        """
        tasks = [self._analyze_single_case_document(doc) for doc in documents]
        results = await asyncio.gather(*tasks)
        return results
