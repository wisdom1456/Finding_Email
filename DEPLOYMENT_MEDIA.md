# Media Processing Deployment Guide

This guide outlines deployment considerations for the media processing capabilities of the Legal Document Analysis Portal.

## Production Environment Setup

### Cloud Credentials
- **Security**: In a production environment, never hardcode credentials or include the service account key in the repository.
- **Recommended Practice**: Use a secret management service provided by your hosting platform (e.g., Streamlit Cloud secrets, Railway secrets, AWS Secrets Manager) to securely store and inject the `GOOGLE_APPLICATION_CREDENTIALS_JSON` content.

### Environment Variables
The following environment variables must be configured in your production environment:

- `OPENAI_API_KEY`: Your OpenAI API key.
- `GCP_PROJECT_ID`: Your Google Cloud project ID.
- `GCP_BUCKET_NAME`: The name of your production Google Cloud Storage bucket.
- `GOOGLE_APPLICATION_CREDENTIALS`: The path to the service account key (if mounted as a file) or the variable holding the JSON content.

## Google Cloud Storage Bucket

- **Production Bucket**: It is recommended to use a separate Google Cloud Storage bucket for production to isolate it from development and testing environments.
- **Permissions**: Ensure the production service account has the necessary permissions (`Storage Admin`) on the production bucket.
- **Lifecycle Policy**: Maintain a strict lifecycle policy (e.g., delete files after 1 day) to manage costs and data retention.

## Performance and Cost

### Performance Monitoring
- **Google Cloud Monitoring**: Use Google Cloud's monitoring tools to track the usage and performance of the Video Intelligence API and Cloud Storage.
- **Application Logging**: Implement detailed logging within the application to monitor the duration of transcription and video analysis tasks.

### Cost Considerations
- **Video Intelligence API**: This is a powerful but potentially expensive service. Monitor usage closely to avoid unexpected costs. Refer to the [Google Cloud pricing page](https://cloud.google.com/video-intelligence/pricing) for details.
- **Cloud Storage**: While temporary storage is cost-effective, ensure the lifecycle policy is active to prevent accumulation of data and associated costs.
- **OpenAI Whisper**: Transcription costs are based on the duration of the audio. Monitor usage via the OpenAI dashboard.

## Backup and Recovery

- **Source Code**: All source code is managed in the Git repository.
- **Cloud Storage**: Since files in the bucket are temporary, no backup is required. The original files are expected to be managed by the user.
- **Configuration**: Securely back up your environment variable configurations.