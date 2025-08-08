"""
JSON Architecture Service

Handles structured JSON generation, validation, and conversion operations for email generation.
This service is responsible for:
- Generating structured JSON responses from AI
- Validating JSON structure and content
- Converting JSON to HTML/email format
- Managing JSON schema compliance

This replaces JSON-related methods from the original EmailGeneratorV2 class.
"""

import json
import re
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class JSONArchitectureService:
    """
    Manages structured JSON operations for email generation.
    
    This service handles the JSON-based architecture that generates structured
    legal content and converts it to various output formats.
    """
    
    def __init__(self):
        """Initialize the JSON architecture service."""
        self.required_sections = [
            'factual_summary',
            'legal_analysis', 
            'evidence_review',
            'recommendations'
        ]
    
    def generate_structured_json(self, ai_response: str) -> Dict[str, Any]:
        """
        Parse and structure AI response into JSON format.
        
        Takes raw AI response and attempts to extract structured content
        organized by legal document sections.
        
        Args:
            ai_response: Raw AI response text
            
        Returns:
            Structured JSON object with legal content sections
        """
        if not ai_response:
            return self._create_empty_structure()
        
        try:
            # First, try to parse if it's already JSON
            if ai_response.strip().startswith('{'):
                try:
                    return json.loads(ai_response)
                except json.JSONDecodeError:
                    pass
            
            # Extract content sections using pattern matching
            structured_content = self._extract_content_sections(ai_response)
            
            # Validate and clean the structured content
            return self._validate_and_clean_structure(structured_content)
            
        except Exception as e:
            logger.warning(f"Error generating structured JSON: {e}")
            return self._create_fallback_structure(ai_response)
    
    def validate_json_response(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate JSON response structure and content.
        
        Ensures the JSON response contains all required sections and
        has valid content structure.
        
        Args:
            json_data: JSON data to validate
            
        Returns:
            Validated and potentially corrected JSON structure
        """
        if not isinstance(json_data, dict):
            logger.warning("JSON data is not a dictionary")
            return self._create_empty_structure()
        
        validated_data = {}
        
        # Ensure all required sections exist
        for section in self.required_sections:
            if section in json_data:
                validated_data[section] = self._validate_section_content(
                    json_data[section], section
                )
            else:
                logger.warning(f"Missing required section: {section}")
                validated_data[section] = f"[{section.replace('_', ' ').title()} content not available]"
        
        # Add metadata if present
        if 'metadata' in json_data:
            validated_data['metadata'] = json_data['metadata']
        else:
            validated_data['metadata'] = {
                'generation_timestamp': None,
                'confidence_score': None
            }
        
        return validated_data
    
    def convert_json_to_generated_letter(self, json_data: Dict[str, Any], 
                                       template_content: str = None) -> str:
        """
        Convert structured JSON to formatted letter content.
        
        Takes validated JSON structure and converts it to a formatted
        legal letter or email.
        
        Args:
            json_data: Validated JSON structure
            template_content: Optional template for formatting
            
        Returns:
            Formatted letter content
        """
        if not json_data:
            return "Unable to generate letter content from JSON data."
        
        try:
            # Build letter content from JSON sections
            letter_parts = []
            
            # Add factual summary
            if 'factual_summary' in json_data and json_data['factual_summary']:
                letter_parts.append("**FACTUAL SUMMARY**")
                letter_parts.append(json_data['factual_summary'])
                letter_parts.append("")
            
            # Add legal analysis
            if 'legal_analysis' in json_data and json_data['legal_analysis']:
                letter_parts.append("**LEGAL ANALYSIS**")
                letter_parts.append(json_data['legal_analysis'])
                letter_parts.append("")
            
            # Add evidence review
            if 'evidence_review' in json_data and json_data['evidence_review']:
                letter_parts.append("**EVIDENCE REVIEW**")
                letter_parts.append(json_data['evidence_review'])
                letter_parts.append("")
            
            # Add recommendations
            if 'recommendations' in json_data and json_data['recommendations']:
                letter_parts.append("**RECOMMENDATIONS**")
                letter_parts.append(json_data['recommendations'])
                letter_parts.append("")
            
            return "\n".join(letter_parts).strip()
            
        except Exception as e:
            logger.error(f"Error converting JSON to letter: {e}")
            return "Error generating letter content from structured data."
    
    def _extract_content_sections(self, text: str) -> Dict[str, str]:
        """
        Extract content sections from unstructured text.
        
        Uses pattern matching to identify and extract different sections
        of legal content from raw text.
        
        Args:
            text: Raw text content
            
        Returns:
            Dictionary with extracted sections
        """
        sections = {}
        
        # Define section patterns
        patterns = {
            'factual_summary': r'(?i)(?:factual\s+summary|summary\s+of\s+facts|facts?)\s*:?\s*(.*?)(?=(?:legal\s+analysis|evidence|recommendation|$))',
            'legal_analysis': r'(?i)(?:legal\s+analysis|analysis|legal\s+review)\s*:?\s*(.*?)(?=(?:evidence|recommendation|facts|$))',
            'evidence_review': r'(?i)(?:evidence\s+review|evidence|review\s+of\s+evidence)\s*:?\s*(.*?)(?=(?:recommendation|legal|facts|$))',
            'recommendations': r'(?i)(?:recommendations?|conclusion|next\s+steps)\s*:?\s*(.*?)$'
        }
        
        for section_name, pattern in patterns.items():
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                if content:
                    sections[section_name] = content
        
        # If no sections found, put everything in factual_summary
        if not sections:
            sections['factual_summary'] = text.strip()
        
        return sections
    
    def _validate_section_content(self, content: Any, section_name: str) -> str:
        """
        Validate and clean content for a specific section.
        
        Args:
            content: Section content to validate
            section_name: Name of the section
            
        Returns:
            Cleaned and validated content
        """
        if not content:
            return f"[{section_name.replace('_', ' ').title()} content not available]"
        
        # Convert to string if not already
        if not isinstance(content, str):
            try:
                content = str(content)
            except:
                return f"[{section_name.replace('_', ' ').title()} content format error]"
        
        # Basic cleanup
        content = content.strip()
        if len(content) < 10:  # Very short content
            return f"[{section_name.replace('_', ' ').title()} content too brief]"
        
        return content
    
    def _create_empty_structure(self) -> Dict[str, Any]:
        """Create an empty but valid JSON structure."""
        return {
            section: f"[{section.replace('_', ' ').title()} content not available]"
            for section in self.required_sections
        }
    
    def _create_fallback_structure(self, original_text: str) -> Dict[str, Any]:
        """
        Create fallback structure when parsing fails.
        
        Args:
            original_text: Original text that failed to parse
            
        Returns:
            Fallback JSON structure
        """
        return {
            'factual_summary': original_text[:500] + "..." if len(original_text) > 500 else original_text,
            'legal_analysis': '[Legal analysis content not available]',
            'evidence_review': '[Evidence review content not available]',
            'recommendations': '[Recommendations content not available]',
            'metadata': {
                'generation_timestamp': None,
                'confidence_score': 'low',
                'fallback_used': True
            }
        }
    
    def _validate_and_clean_structure(self, structure: Dict[str, str]) -> Dict[str, Any]:
        """
        Validate and clean the extracted structure.
        
        Args:
            structure: Raw extracted structure
            
        Returns:
            Validated and cleaned structure
        """
        cleaned = {}
        
        for section in self.required_sections:
            if section in structure:
                cleaned[section] = self._validate_section_content(
                    structure[section], section
                )
            else:
                cleaned[section] = f"[{section.replace('_', ' ').title()} content not available]"
        
        cleaned['metadata'] = {
            'generation_timestamp': None,
            'confidence_score': 'medium',
            'sections_found': len([s for s in structure.keys() if s in self.required_sections])
        }
        
        return cleaned