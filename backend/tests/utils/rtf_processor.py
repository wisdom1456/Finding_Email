from striprtf.striprtf import rtf_to_text as striprtf_to_text
import re

def rtf_to_text(rtf_content):
    """
    Converts RTF content to plain text using striprtf.
    """
    if isinstance(rtf_content, bytes):
        rtf_content = rtf_content.decode('utf-8', errors='ignore')
    text = striprtf_to_text(rtf_content)
    return text

def normalize_text(text):
    """
    Normalizes text by removing extra whitespace and standardizing line breaks.
    """
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text

def extract_structured_content(text):
    """
    Extracts structured content from the email body.
    (This is a placeholder and needs a more robust implementation based on email structure)
    """
    sections = {}
    # Example: A simple way to split by presumed sections
    # This will need to be adapted to the actual email format
    for line in text.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            sections[key.strip()] = value.strip()
    return sections