import os
import json
from scripts.calculate_metrics import main as run_metrics

# Create mock session
session_id = "mock_test_session"
session_path = os.path.join("debug_output", "sessions", session_id)
os.makedirs(session_path, exist_ok=True)

# Stage 1: Raw Text
with open(os.path.join(session_path, "stage1_raw_text.json"), "w") as f:
    json.dump({
        "data": {
            "case_docs": {
                "contract.txt": "This contract between John Doe and Jane Smith states that John owes Jane $1000 for roofing work done in Miami on 2025-01-01."
            }
        }
    }, f)

# Stage 3: Summaries
with open(os.path.join(session_path, "stage3_document_summaries.json"), "w") as f:
    json.dump({
        "data": [
            {
                "document_name": "contract.txt",
                "executive_summary": "Contract between John Doe and Jane Smith.",
                "key_content": "John Doe owes $1000 for roofing."
            }
        ]
    }, f)

# Stage 4: Synthesis
with open(os.path.join(session_path, "stage4_case_synthesis.json"), "w") as f:
    json.dump({
        "data": {
            "case_summary": "John Doe and Jane Smith roofing dispute.",
            "key_issues": ["Unpaid debt of $1000"]
        }
    }, f)

# Stage 5: Final Letter
with open(os.path.join(session_path, "stage5_final_letter.txt"), "w") as f:
    f.write("Dear Jane Smith, John Doe owes you $1000 for the Miami project.")

print(f"Mock session created at {session_path}")




