"""
Assembles the final letter by populating a template with generated content.
"""

from __future__ import annotations

import logging

from jinja2 import Environment, FileSystemLoader


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def populate_template(content_blocks: dict[str, str], template_path: str) -> str:
    """
    Populates a Jinja2 template with the provided content blocks.

    Args:
        content_blocks: A dictionary of content blocks (e.g., introduction, body).
        template_path: The file path to the Jinja2 template.

    Returns:
        The rendered HTML content as a string.
    """
    logging.info(f"Entering populate_template with template: {template_path}")
    try:
        # Set up Jinja2 environment
        env = Environment(loader=FileSystemLoader("."))
        template = env.get_template(template_path)

        # Render the template
        rendered_html = template.render(content_blocks)
        logging.info("Exiting populate_template.")
        return rendered_html
    except Exception as e:
        logging.exception(f"Error populating template: {e}")
        raise


if __name__ == "__main__":
    logging.info("template_assembler.py is being run standalone for testing.")

    # Create a dummy template file
    with open("test_template.html", "w") as f:
        f.write("<h1>{{ introduction }}</h1><p>{{ body }}</p><p>{{ conclusion }}</p>")

    # Example content blocks
    mock_content = {
        "introduction": "Test Introduction",
        "body": "This is a test body.",
        "conclusion": "This is a test conclusion.",
    }

    # Populate the template
    try:
        final_html = populate_template(mock_content, "test_template.html")
        logging.info("Template populated successfully.")
        logging.info(f"Rendered HTML:\n{final_html}")
    except Exception as e:
        logging.exception(f"Failed to populate template: {e}")
