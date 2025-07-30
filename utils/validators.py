"""
Utility functions for validation.
"""

def validate_form(case_info):
    """
    Validates the case information form.
    Placeholder for future implementation.
    """
    print("Validating form...")
    if not case_info.get("clientName") or not case_info.get("attorneyName"):
        return False, "Client and Attorney names are required."
    return True, "Form is valid."

def validate_file(file):
    """
    Validates a single file.
    Placeholder for future implementation.
    """
    # In the future, this will check file size, type, etc.
    print(f"Validating file: {file.name}")
    return True, "File is valid."