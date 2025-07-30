import requests
import json
import os

# Define the URL of the FastAPI endpoint
url = "http://localhost:8000/api/v1/analysis/full-pipeline"

# Define the paths to the files to be uploaded
intake_form_path = './samples/Badam, Balaji [MetLife]/Client Docs/Intake (General) - Balaji Badam.pdf'
case_document_paths = [
    './samples/Badam, Balaji [MetLife]/Client Docs/imessage - Breanna communication 1.jpg'
]

files_data = []
all_files_exist = True

# Prepare intake form
if os.path.exists(intake_form_path):
    files_data.append(
        ('intake_form', (os.path.basename(intake_form_path), open(intake_form_path, 'rb'), 'application/pdf'))
    )
else:
    print(f"File not found: {intake_form_path}")
    all_files_exist = False
    
# Prepare case documents
for path in case_document_paths:
    if os.path.exists(path):
        files_data.append(
            ('case_documents', (os.path.basename(path), open(path, 'rb'), 'image/jpeg'))
        )
    else:
        print(f"File not found: {path}")
        all_files_exist = False

# Check if there are files to upload
if not all_files_exist or not files_data:
    print("One or more files were not found. Exiting.")
    # Clean up any opened files
    for _, (name, f, mime) in files_data:
        f.close()
else:
    # Send the POST request
    try:
        response = requests.post(url, files=files_data)
        
        # Close the files
        for _, (name, f, mime) in files_data:
            f.close()
            
        # Check if the request was successful
        if response.status_code == 200:
            # Pretty-print the JSON response
            print(json.dumps(response.json(), indent=4))
        else:
            print(f"Request failed with status code: {response.status_code}")
            print("Response:")
            print(response.text)
            
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
