"""
Template Rendering Service

Handles Jinja2 template rendering and management for email generation.
This service is responsible for:
- Loading and rendering Jinja2 templates
- Managing template context and variables
- Handling template inheritance and includes
- Template error handling and fallbacks

This replaces template-related methods from the original EmailGeneratorV2 class.
"""

import os
from typing import Dict, Any, Optional, List
import logging
from jinja2 import Environment, FileSystemLoader, Template, TemplateError, select_autoescape

logger = logging.getLogger(__name__)


class TemplateRenderingService:
    """
    Manages Jinja2 template rendering for email generation.
    
    This service provides a centralized way to handle all template operations,
    including loading, rendering, and error handling.
    """
    
    def __init__(self, template_directory: Optional[str] = None):
        """
        Initialize the template rendering service.
        
        Args:
            template_directory: Path to template directory
        """
        self.template_directory = template_directory
        self.jinja_env = None
        self._setup_jinja_environment()
    
    def _setup_jinja_environment(self):
        """
        Set up the Jinja2 environment with appropriate settings.
        """
        if self.template_directory and os.path.exists(self.template_directory):
            try:
                self.jinja_env = Environment(
                    loader=FileSystemLoader(self.template_directory),
                    autoescape=select_autoescape(['html', 'xml']),
                    trim_blocks=True,
                    lstrip_blocks=True
                )
                logger.info(f"Jinja2 environment initialized with template directory: {self.template_directory}")
            except Exception as e:
                logger.error(f"Error setting up Jinja2 environment: {e}")
                self.jinja_env = None
        else:
            logger.warning(f"Template directory not found or not provided: {self.template_directory}")
            self.jinja_env = None
    
    def render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render a template with the provided context.
        
        Args:
            template_name: Name of the template file
            context: Dictionary of variables for template rendering
            
        Returns:
            Rendered template content
        """
        if not self.jinja_env:
            logger.error("Jinja2 environment not initialized")
            return self._generate_fallback_content(template_name, context)
        
        try:
            template = self.jinja_env.get_template(template_name)
            rendered_content = template.render(**context)
            logger.info(f"Successfully rendered template: {template_name}")
            return rendered_content
            
        except TemplateError as e:
            logger.error(f"Template error rendering {template_name}: {e}")
            return self._generate_fallback_content(template_name, context)
        except Exception as e:
            logger.error(f"Unexpected error rendering template {template_name}: {e}")
            return self._generate_fallback_content(template_name, context)
    
    def render_string_template(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Render a template from a string rather than a file.
        
        Args:
            template_string: Template content as string
            context: Dictionary of variables for template rendering
            
        Returns:
            Rendered template content
        """
        try:
            if self.jinja_env:
                template = self.jinja_env.from_string(template_string)
            else:
                # Create minimal environment for string rendering
                env = Environment(autoescape=select_autoescape(['html', 'xml']))
                template = env.from_string(template_string)
            
            rendered_content = template.render(**context)
            logger.info("Successfully rendered string template")
            return rendered_content
            
        except TemplateError as e:
            logger.error(f"Template error rendering string template: {e}")
            return f"Template rendering error: {e}"
        except Exception as e:
            logger.error(f"Unexpected error rendering string template: {e}")
            return f"Unexpected template error: {e}"
    
    def get_available_templates(self) -> List[str]:
        """
        Get list of available templates in the template directory.
        
        Returns:
            List of template file names
        """
        if not self.template_directory or not os.path.exists(self.template_directory):
            return []
        
        try:
            templates = []
            for file in os.listdir(self.template_directory):
                if file.endswith(('.html', '.jinja2', '.j2', '.txt')):
                    templates.append(file)
            return sorted(templates)
        except Exception as e:
            logger.error(f"Error listing templates: {e}")
            return []
    
    def template_exists(self, template_name: str) -> bool:
        """
        Check if a template file exists.
        
        Args:
            template_name: Name of the template file
            
        Returns:
            True if template exists, False otherwise
        """
        if not self.template_directory:
            return False
        
        template_path = os.path.join(self.template_directory, template_name)
        return os.path.exists(template_path)
    
    def prepare_email_context(self, case_data: Dict[str, Any], 
                            additional_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Prepare context variables for email template rendering.
        
        Args:
            case_data: Primary case/legal data
            additional_context: Additional context variables
            
        Returns:
            Complete context dictionary for template rendering
        """
        context = {
            # Standard template variables
            'case_data': case_data,
            'current_date': None,  # Could be set by caller
            'attorney_name': None,  # Could be set by caller
            'firm_name': None,     # Could be set by caller
            
            # Content sections
            'factual_summary': case_data.get('factual_summary', ''),
            'legal_analysis': case_data.get('legal_analysis', ''),
            'evidence_review': case_data.get('evidence_review', ''),
            'recommendations': case_data.get('recommendations', ''),
            
            # Metadata
            'confidence_score': case_data.get('metadata', {}).get('confidence_score', 'medium'),
            'generation_timestamp': case_data.get('metadata', {}).get('generation_timestamp', None),
            
            # Formatting helpers
            'format_section_header': self._format_section_header,
            'format_bullet_points': self._format_bullet_points,
        }
        
        # Add additional context if provided
        if additional_context:
            context.update(additional_context)
        
        return context
    
    def format_video_analysis_for_appendix(self, video_analysis: str) -> str:
        """
        Format video analysis content for appendix inclusion.
        
        Args:
            video_analysis: Raw video analysis content
            
        Returns:
            Formatted video analysis for appendix
        """
        if not video_analysis:
            return "No video analysis available."
        
        try:
            # Basic formatting for appendix
            formatted_content = video_analysis.strip()
            
            # Add section header if not present
            if not formatted_content.upper().startswith('VIDEO ANALYSIS'):
                formatted_content = f"VIDEO ANALYSIS\n\n{formatted_content}"
            
            # Ensure proper paragraph spacing
            formatted_content = formatted_content.replace('\n\n\n', '\n\n')
            
            return formatted_content
            
        except Exception as e:
            logger.error(f"Error formatting video analysis: {e}")
            return video_analysis
    
    def _generate_fallback_content(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Generate fallback content when template rendering fails.
        
        Args:
            template_name: Name of the failed template
            context: Context that was being used
            
        Returns:
            Fallback content
        """
        fallback_parts = [
            f"[Template rendering failed for: {template_name}]",
            "",
            "**FACTUAL SUMMARY**",
            context.get('factual_summary', '[Factual summary not available]'),
            "",
            "**LEGAL ANALYSIS**", 
            context.get('legal_analysis', '[Legal analysis not available]'),
            "",
            "**EVIDENCE REVIEW**",
            context.get('evidence_review', '[Evidence review not available]'),
            "",
            "**RECOMMENDATIONS**",
            context.get('recommendations', '[Recommendations not available]'),
        ]
        
        return "\n".join(fallback_parts)
    
    def _format_section_header(self, header_text: str) -> str:
        """
        Format a section header for consistent styling.
        
        Args:
            header_text: Header text to format
            
        Returns:
            Formatted header
        """
        return f"**{header_text.upper()}**"
    
    def _format_bullet_points(self, content: str) -> str:
        """
        Format content with consistent bullet points.
        
        Args:
            content: Content to format with bullet points
            
        Returns:
            Content with formatted bullet points
        """
        if not content:
            return content
        
        lines = content.split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('•') and not line.startswith('-'):
                # Add bullet point if line looks like a list item
                if any(line.startswith(prefix) for prefix in ['1.', '2.', '3.', 'a.', 'b.', 'c.', '*']):
                    formatted_lines.append(f"• {line}")
                else:
                    formatted_lines.append(line)
            else:
                formatted_lines.append(line)
        
        return '\n'.join(formatted_lines)
    
    def update_template_directory(self, new_directory: str):
        """
        Update the template directory and reinitialize Jinja environment.
        
        Args:
            new_directory: New template directory path
        """
        self.template_directory = new_directory
        self._setup_jinja_environment()
        logger.info(f"Template directory updated to: {new_directory}")