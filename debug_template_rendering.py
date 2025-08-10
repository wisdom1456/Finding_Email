#!/usr/bin/env python3
"""
A debug script to test Jinja2 template rendering directly,
isolated from the full application logic.
"""

from __future__ import annotations

import os
import sys

from jinja2 import Environment, FileSystemLoader

from utils.logging_config import setup_logging


logger = setup_logging("template_renderer_debug")


# Add the project root to the Python path for module imports
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(project_root, ".."))


def load_template_from_file(template_path: str):
    """Load a Jinja2 template from a given file path."""
    template_dir = os.path.dirname(template_path)
    template_name = os.path.basename(template_path)
    env = Environment(loader=FileSystemLoader(template_dir))
    return env.get_template(template_name)


def render_template_with_context(template, context: dict):
    """Render the given template with the provided context."""
    logger.debug(f"Attempting to render template with context keys: {context.keys()}")
    return template.render(context)


def create_mock_context():
    """Create a mock context dictionary for template rendering."""
    logger.debug("Creating mock context...")
    return {
        "client_name": "John Doe",
        "attorney_name": "Jane Lawyer",
        "case_summary": "This is a summary of a test case for template rendering.",
        "firm_name": "LegalFirm Inc.",
        "generated_letter": {  # Mock structure based on expected output for findings_email.jinja2
            "background_summary": "This is a background summary.",
            "analysis_and_position": "Here is the legal analysis and position.",
            "recommendations": "These are the recommendations.",
            "disclaimer": "This is a disclaimer.",
            "next_steps": [
                {"step_number": 1, "description": "Gather more documents"},
                {"step_number": 2, "description": "Schedule client meeting"},
            ],
            "conclusion": "Conclusion of the letter.",
        },
        "current_date": "2023-10-27",
        "current_year": "2023",
        "attachments_summary": "List of attached documents.",
    }


def main():
    logger.info("Testing Jinja2 Template Rendering")
    logger.info("=" * 40)

    try:
        template_file_path = "backend/assets/templates/budget_sheet.jinja2"  # Update to a relevant template
        logger.info(f"Loading template from: {template_file_path}")
        template = load_template_from_file(template_file_path)
        logger.info("Template loaded successfully.")

        context = create_mock_context()
        logger.info("Mock context created.")

        rendered_content = render_template_with_context(template, context)
        logger.info("Template rendered successfully.")

        output_file = "debug_template_output.html"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(rendered_content)
        logger.info(f"Rendered content saved to: {output_file}")

        logger.info("\nPreview of rendered content (first 500 chars):")
        logger.info("-" * 40)
        logger.info(rendered_content[:500] + "...")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
