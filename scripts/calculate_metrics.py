import os
import json
import argparse
from legal_portal.utils.quality_metrics import calculate_retention_metrics

def main():
    parser = argparse.ArgumentParser(description="Calculate quality metrics for a diagnostic session.")
    parser.add_argument("session_id", help="Session ID from debug_output/sessions/")
    args = parser.parse_args()
    
    session_path = os.path.join("debug_output", "sessions", args.session_id)
    if not os.path.exists(session_path):
        print(f"Error: Session path {session_path} does not exist.")
        return
    
    stages_data = {}
    
    # Load Stage 1
    s1_path = os.path.join(session_path, "stage1_raw_text.json")
    if os.path.exists(s1_path):
        with open(s1_path, "r") as f:
            stages_data["raw_text"] = json.load(f)["data"]["case_docs"]
            
    # Load Stage 3
    s3_path = os.path.join(session_path, "stage3_document_summaries.json")
    if os.path.exists(s3_path):
        with open(s3_path, "r") as f:
            stages_data["document_summaries"] = json.load(f)["data"]
            
    # Load Stage 4
    s4_path = os.path.join(session_path, "stage4_case_synthesis.json")
    if os.path.exists(s4_path):
        with open(s4_path, "r") as f:
            stages_data["case_synthesis"] = json.load(f)["data"]
            
    # Load Stage 5
    s5_path = os.path.join(session_path, "stage5_final_letter.txt")
    if os.path.exists(s5_path):
        with open(s5_path, "r") as f:
            stages_data["final_letter"] = f.read()
            
    metrics = calculate_retention_metrics(stages_data)
    
    print(f"--- Quality Metrics for Session {args.session_id} ---")
    for key, value in metrics.items():
        print(f"{key}: {value:.2%}")
        
    # Save metrics back to session folder
    with open(os.path.join(session_path, "quality_report.json"), "w") as f:
        json.dump(metrics, f, indent=2)

if __name__ == "__main__":
    main()




