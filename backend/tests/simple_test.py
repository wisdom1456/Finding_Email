import requests
import json
import os

# Define the URL of the FastAPI synchronous endpoint
url = "http://127.0.0.1:8000/api/v1/analysis/full-pipeline"

# Define the paths to the files to be uploaded
intake_form_path = '../../samples/Badam, Balaji [MetLife]/Client Docs/Intake (General) - Balaji Badam.pdf'
case_document_paths = [
    '../../samples/Badam, Balaji [MetLife]/Client Docs/imessage - Breanna communication 1.jpg'
]

def read_file_content(file_path):
    """Read file content into memory."""
    try:
        with open(file_path, 'rb') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None

# Read files into memory first
files_data = []
all_files_exist = True

print("Reading intake form...")
if os.path.exists(intake_form_path):
    intake_content = read_file_content(intake_form_path)
    if intake_content:
        files_data.append(
            ('intake_form', (os.path.basename(intake_form_path), intake_content, 'application/pdf'))
        )
        print(f"✓ Intake form loaded: {os.path.basename(intake_form_path)} ({len(intake_content)} bytes)")
    else:
        print(f"Failed to read: {intake_form_path}")
        all_files_exist = False
else:
    print(f"File not found: {intake_form_path}")
    all_files_exist = False
    
print("Reading case documents...")
for path in case_document_paths:
    if os.path.exists(path):
        case_content = read_file_content(path)
        if case_content:
            files_data.append(
                ('case_documents', (os.path.basename(path), case_content, 'image/jpeg'))
            )
            print(f"✓ Case document loaded: {os.path.basename(path)} ({len(case_content)} bytes)")
        else:
            print(f"Failed to read: {path}")
            all_files_exist = False
    else:
        print(f"File not found: {path}")
        all_files_exist = False

# Check if there are files to upload
if not all_files_exist or not files_data:
    print("One or more files were not found or could not be read. Exiting.")
else:
    print(f"\nSending request to: {url}")
    print(f"Files to upload: {len(files_data)}")
    
    # Send the POST request with synchronous processing
    try:
        response = requests.post(url, files=files_data, timeout=300)
        
        if response.status_code == 200:
            print("✓ Request successful! Processing completed.")
            
            try:
                result = response.json()
                print("\n" + "="*60)
                print("RESPONSE SUMMARY")
                print("="*60)
                
                # Check if analysis was completed
                if result.get('analysis'):
                    analysis = result['analysis']
                    print(f"✓ Analysis completed")
                    
                    # Check intake analysis
                    if analysis.get('intake_analysis'):
                        intake = analysis['intake_analysis']
                        print(f"✓ Intake Analysis - Client: {intake.get('client_name', 'N/A')}")
                        print(f"  Case Type: {intake.get('case_type', 'N/A')}")
                        print(f"  Urgency: {intake.get('urgency_level', 'N/A')}")
                    
                    # Check case analyses
                    if analysis.get('case_analyses'):
                        print(f"✓ Case Documents Analyzed: {len(analysis['case_analyses'])}")
                        for i, doc_analysis in enumerate(analysis['case_analyses']):
                            print(f"  {i+1}. {doc_analysis.get('document_title', 'Untitled')}")
                    
                    # Check legal assessment
                    if analysis.get('legal_assessment'):
                        legal = analysis['legal_assessment']
                        print(f"✓ Legal Assessment - Claim Viability: {legal.get('claim_viability', 'N/A')}")
                
                # Check email generation
                if result.get('email'):
                    email_response = result['email']
                    print(f"✓ Email Generated")
                    
                    # Check download links
                    if email_response.get('download_links'):
                        print(f"✓ Download Links Created: {len(email_response['download_links'])}")
                        for link in email_response['download_links']:
                            print(f"  - {link.get('file_name', 'Unknown')}")
                    else:
                        print("✗ No download links found")
                    
                    # Check case analysis text
                    if email_response.get('case_analysis_text'):
                        analysis_text = email_response['case_analysis_text']
                        print(f"✓ Case Analysis Text Generated ({len(analysis_text)} characters)")
                    else:
                        print("✗ No case analysis text found")
                else:
                    print("✗ No email response found")
                
                # Check for errors
                if result.get('errors') or (result.get('analysis') and result['analysis'].get('errors')):
                    all_errors = result.get('errors', [])
                    if result.get('analysis') and result['analysis'].get('errors'):
                        all_errors.extend(result['analysis']['errors'])
                    
                    print(f"\n⚠️  ERRORS FOUND: {len(all_errors)}")
                    for error in all_errors:
                        print(f"  - {error.get('source', 'Unknown')}: {error.get('error_message', 'No message')}")
                
                print("\n" + "="*60)
                print("FULL RESPONSE (JSON)")
                print("="*60)
                print(json.dumps(result, indent=2, default=str))
                
            except json.JSONDecodeError as e:
                print(f"✗ Failed to parse JSON response: {e}")
                print("Raw response:")
                print(response.text)
                
        else:
            print(f"✗ Request failed with status code: {response.status_code}")
            print("Response:")
            print(response.text)
            
    except requests.exceptions.Timeout:
        print("✗ Request timed out after 300 seconds")
    except requests.exceptions.RequestException as e:
        print(f"✗ An error occurred: {e}")
