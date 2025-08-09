from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from backend.utils.data_models import CaseAnalysisResult
from backend_logic.config import get_openai_config


class JsonProcessingService:
    """
    Simplified service for generating HTML content using the new single master prompt.
    
    This refactored service aligns with the new architectural approach:
    - Uses a single, authoritative master prompt
    - Injects CaseAnalysisResult directly into the prompt
    - Generates HTML directly instead of multi-step JSON processing
    - Removes complex multi-prompt chaining logic
    """
    
    def __init__(self, client: OpenAI, config: dict[str, Any]):
        self.client = client
        self.config = config

    def generate_html_letter(self, analysis: CaseAnalysisResult) -> str:
        """
        Generate HTML letter content using the single master prompt.
        
        This replaces the old generate_structured_json method with a simplified
        approach that directly generates the final HTML letter.
        
        Args:
            analysis: Complete case analysis result
            
        Returns:
            Generated HTML letter content
        """
        try:
            print("EMAIL GENERATOR V2: Generating HTML letter using master prompt...")

            # Extract client information from analysis
            client_name = analysis.intake_analysis.client_name if analysis.intake_analysis else "Client"
            case_type = analysis.intake_analysis.case_type if analysis.intake_analysis else "Legal Matter"

            # CAPTURE DATA: Save the final analysis data to JSON file
            try:
                os.makedirs("validation_output", exist_ok=True)
                final_analysis_data = analysis.model_dump_json(indent=2)
                
                with open("validation_output/final_analysis_data.json", "w", encoding="utf-8") as f:
                    f.write(final_analysis_data)
                print("EMAIL GENERATOR V2: ✅ Saved final analysis data to validation_output/final_analysis_data.json")
            except Exception as save_error:
                print(f"EMAIL GENERATOR V2: ⚠️ Failed to save analysis data: {save_error}")

            # Get the master prompt from configuration
            master_prompt = self.config.get("master_prompt")
            if not master_prompt:
                raise ValueError("Master prompt not found in configuration")

            # Inject case analysis directly into the master prompt
            formatted_prompt = master_prompt.format(
                client_name=client_name,
                case_type=case_type,
                analysis=analysis.model_dump_json(indent=2)
            )

            # CAPTURE PROMPT: Save the fully constructed prompt to text file
            try:
                with open("validation_output/final_prompt.txt", "w", encoding="utf-8") as f:
                    f.write(formatted_prompt)
                print("EMAIL GENERATOR V2: ✅ Saved final prompt to validation_output/final_prompt.txt")
            except Exception as save_error:
                print(f"EMAIL GENERATOR V2: ⚠️ Failed to save prompt: {save_error}")

            print("EMAIL GENERATOR V2: Making OpenAI request with master prompt")
            html_response = self._make_openai_request(formatted_prompt)

            if not html_response or not html_response.strip():
                raise ValueError("OpenAI returned empty response for HTML generation")

            # Clean and validate the HTML response
            cleaned_html = self._clean_html_response(html_response)
            validated_html = self._validate_html_structure(cleaned_html)

            print(f"EMAIL GENERATOR V2: ✅ Successfully generated HTML letter ({len(validated_html)} characters)")
            return validated_html

        except Exception as e:
            print(f"EMAIL GENERATOR V2: ❌ HTML letter generation failed: {e}")
            return self._generate_fallback_html(client_name, case_type, str(e))

    def _clean_html_response(self, response_text: str) -> str:
        """
        Clean OpenAI response to extract valid HTML.
        
        Args:
            response_text: Raw OpenAI response
            
        Returns:
            Cleaned HTML content
        """
        if not response_text:
            return ""

        # Remove markdown code fences if present
        cleaned = re.sub(r"^```html\s*", "", response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"^```\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        # Extract HTML if wrapped in tags
        html_start = cleaned.find("<html")
        html_end = cleaned.rfind("</html>")
        
        if html_start != -1 and html_end != -1 and html_end > html_start:
            cleaned = cleaned[html_start:html_end + 7]  # Include </html>
        elif "<body>" in cleaned:
            # If no <html> tags but has <body>, extract body content
            body_start = cleaned.find("<body>")
            body_end = cleaned.rfind("</body>")
            if body_start != -1 and body_end != -1:
                body_content = cleaned[body_start + 6:body_end]
                cleaned = f"<html><body>{body_content}</body></html>"

        return cleaned

    def _validate_html_structure(self, html_content: str) -> str:
        """
        Validate HTML structure and ensure basic compliance.
        
        Args:
            html_content: HTML content to validate
            
        Returns:
            Validated HTML content
        """
        if not html_content:
            return self._generate_minimal_fallback_html()

        # Ensure basic HTML structure
        if not html_content.startswith("<html"):
            if "<body>" in html_content:
                html_content = f"<html>{html_content}</html>"
            else:
                html_content = f"<html><body>{html_content}</body></html>"

        # Ensure closing tags
        if "<html>" in html_content and "</html>" not in html_content:
            html_content += "</html>"
        
        if "<body>" in html_content and "</body>" not in html_content:
            html_content = html_content.replace("</html>", "</body></html>")

        return html_content

    def _generate_fallback_html(self, client_name: str, case_type: str, error_message: str) -> str:
        """
        Generate fallback HTML content when main generation fails.
        
        Args:
            client_name: Client name
            case_type: Case type
            error_message: Error description
            
        Returns:
            Fallback HTML content
        """
        return f"""<html>
<body>
<p>We have completed our review of your {case_type.lower()} matter. Due to a technical issue during document generation, we are providing this preliminary communication.</p>

<p>We are currently analyzing the details of your case and will provide a comprehensive findings letter within 24 hours. Our initial review indicates that your matter requires immediate attention and strategic consideration.</p>

<p><strong>Immediate Next Steps:</strong></p>
<ul>
<li>We will contact you within 24 hours with a detailed analysis</li>
<li>Please preserve all relevant documents and communications</li>
<li>Do not take any action regarding this matter until we provide guidance</li>
</ul>

<p>If you have urgent questions or concerns, please contact our office immediately. We are committed to providing you with thorough legal guidance and will resolve this technical issue promptly.</p>

<p>Thank you for your patience as we ensure you receive the most accurate and comprehensive legal analysis possible.</p>
</body>
</html>"""

    def _generate_minimal_fallback_html(self) -> str:
        """Generate minimal fallback HTML when all else fails."""
        return """<html>
<body>
<p>We are currently preparing your legal analysis and will contact you shortly with detailed findings.</p>
<p>Please contact our office if you have any immediate concerns.</p>
</body>
</html>"""

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type((RateLimitError, APIError, APITimeoutError, APIConnectionError, InternalServerError)))
    def _make_openai_request(self, prompt: str, model: str | None = None) -> str | None:
        """Make OpenAI API request with comprehensive error handling following OpenAI best practices."""
        api_log_entry = {
            "module": "EmailGeneratorV2", 
            "method": "_make_openai_request", 
            "hypothesis_id": "openai_api_failure", 
            "stage": "entry", 
            "prompt_length": len(prompt), 
            "model_provided": model, 
            "config_available": self.config is not None, 
            "timestamp": datetime.now().isoformat()
        }
        print(f"EMAIL_GENERATOR_DEBUG: {json.dumps(api_log_entry)}")
        
        config = get_openai_config()
        model = model or config["model"]
        
        print(f"EMAIL GENERATOR V2: 🔍 Making OpenAI request with model: {model}")
        print(f"EMAIL GENERATOR V2: 🔍 Prompt length: {len(prompt)} characters")
        
        try:
            response = self.client.with_options(
                timeout=config["timeout"], 
                max_retries=config["max_retries"]
            ).chat.completions.create(
                model=model, 
                messages=[
                    {"role": "user", "content": prompt}
                ], 
                temperature=config["temperature"], 
                max_tokens=config["max_tokens"]
            )
            
            request_id = getattr(response, "_request_id", "unknown")
            content = response.choices[0].message.content
            
            print(f"EMAIL GENERATOR V2: ✅ OpenAI request successful, response length: {len(content) if content else 0}")
            
            if not content or not content.strip():
                print(f"EMAIL GENERATOR V2: ❌ OpenAI returned empty content (Request ID: {request_id})")
                return None
            
            return content
            
        except APIConnectionError as e:
            print("EMAIL GENERATOR V2: ❌ API Connection Error: The server could not be reached")
            print(f"EMAIL GENERATOR V2: 🔍 Underlying cause: {e.__cause__}")
            raise
        except RateLimitError as e:
            print(f"EMAIL GENERATOR V2: ❌ Rate Limit Error (429): {e}")
            print("EMAIL GENERATOR V2: 🔍 Backing off and retrying...")
            raise
        except AuthenticationError as e:
            print(f"EMAIL GENERATOR V2: ❌ Authentication Error (401): {e}")
            print("EMAIL GENERATOR V2: 🔍 Check OpenAI API key configuration")
            return None
        except PermissionDeniedError as e:
            print(f"EMAIL GENERATOR V2: ❌ Permission Denied (403): {e}")
            return None
        except BadRequestError as e:
            print(f"EMAIL GENERATOR V2: ❌ Bad Request (400): {e}")
            print(f"EMAIL GENERATOR V2: 🔍 Model: {model}, Prompt start: {prompt[:200]}...")
            return None
        except UnprocessableEntityError as e:
            print(f"EMAIL GENERATOR V2: ❌ Unprocessable Entity (422): {e}")
            return None
        except APIStatusError as e:
            request_id = getattr(e, "request_id", "unknown")
            print(f"EMAIL GENERATOR V2: ❌ API Status Error: {e.status_code}")
            print(f"EMAIL GENERATOR V2: 🔍 Request ID: {request_id}")
            return None
        except APITimeoutError as e:
            print(f"EMAIL GENERATOR V2: ❌ Request Timeout: {e}")
            raise
        except APIError as e:
            print(f"EMAIL GENERATOR V2: ❌ General API Error: {e}")
            raise
        except (ValueError, TypeError, AttributeError, KeyError, OSError) as e:
            print(f"EMAIL GENERATOR V2: ❌ Unexpected error: {type(e).__name__}: {e}")
            print(f"EMAIL GENERATOR V2: 🔍 Model: {model}, Prompt start: {prompt[:200]}...")
            return None