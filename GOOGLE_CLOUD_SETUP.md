# Google Cloud Platform (GCP) Setup Guide

This guide provides step-by-step instructions for setting up the necessary Google Cloud services for the Legal Document Analysis Portal's media processing features.

## 1. Project Setup

1.  **Create a new GCP Project**: If you don't have one already, create a new project in the [Google Cloud Console](https://console.cloud.google.com/).
2.  **Enable APIs**: Enable the following APIs for your project:
    *   Google Cloud Storage API
    *   Google Cloud Video Intelligence API
3.  **Billing**: Ensure that billing is enabled for your project.

## 2. Service Account Configuration

A service account is required to securely authenticate the application with Google Cloud services.

1.  **Create a Service Account**:
    *   Navigate to "IAM & Admin" > "Service Accounts".
    *   Click "Create Service Account".
    *   Provide a name (e.g., "media-processing-service") and description.
2.  **Grant Permissions**: Assign the following roles to the service account:
    *   `Storage Admin`: For managing files in Google Cloud Storage.
    *   `Video Intelligence Admin`: For accessing the Video Intelligence API.
3.  **Create a Key**:
    *   Once the service account is created, create a JSON key for it.
    *   Download the key and store it securely. **Do not commit this file to version control.**

## 3. Google Cloud Storage Bucket Setup

A bucket is needed to temporarily store video files for analysis.

1.  **Create a Bucket**:
    *   Navigate to "Cloud Storage" > "Buckets".
    *   Click "Create Bucket".
    *   Choose a unique name for your bucket.
    *   Select a region and storage class that meets your needs.
2.  **Configure Lifecycle Policy**:
    *   To automatically delete temporary files, create a lifecycle rule for the bucket.
    *   Set the rule to delete objects after 1 day. This minimizes storage costs and enhances privacy.

## 4. Environment Variable Configuration

The application requires the following environment variables to connect to Google Cloud:

```
# .env
GCP_PROJECT_ID="your-gcp-project-id"
GCP_BUCKET_NAME="your-gcp-bucket-name"
GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
```

-   `GCP_PROJECT_ID`: Your Google Cloud project ID.
-   `GCP_BUCKET_NAME`: The name of the Cloud Storage bucket you created.
-   `GOOGLE_APPLICATION_CREDENTIALS`: The absolute path to the JSON service account key you downloaded.

With these steps completed, the application will be able to securely access Google Cloud services for video processing.