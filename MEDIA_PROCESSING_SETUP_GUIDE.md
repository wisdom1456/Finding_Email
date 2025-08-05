# Media Processing Setup Guide

## Overview
This guide provides step-by-step instructions for setting up the complete media processing pipeline for the Legal Document Analysis Portal.

## 🎯 Current Status
After systematic debugging, we've identified and resolved the actual runtime issues:

### ✅ Issues Resolved
- **Environment Loading**: Fixed `.env` file loading with `python-dotenv`
- **Enhanced Error Handling**: Implemented robust retry logic for Google Cloud service provisioning
- **Code Structure**: Confirmed all original reported issues were already resolved

### ⚠️ Remaining Setup Steps
1. **Enable Google Cloud Speech-to-Text API** (one-time)
2. **Wait for Vertex AI Service Agent Provisioning** (automatic)

## 🔧 Required Google Cloud APIs

### 1. Vertex AI API
- **Status**: ✅ Enabled (service agents being provisioned)
- **Used for**: Video content analysis and insights generation
- **Setup**: Automatic provisioning in progress (5-15 minutes)

### 2. Cloud Speech-to-Text API
- **Status**: ❌ Needs to be enabled
- **Used for**: Audio transcription from video files
- **Enable URL**: https://console.developers.google.com/apis/api/speech.googleapis.com/overview?project=891496644205

### 3. Cloud Storage API
- **Status**: ✅ Enabled and working
- **Used for**: Temporary video file storage during processing

## 📋 Setup Instructions

### Step 1: Enable Speech-to-Text API
1. Visit: https://console.developers.google.com/apis/api/speech.googleapis.com/overview?project=891496644205
2. Click "Enable API"
3. Wait 2-3 minutes for API to propagate

### Step 2: Verify Setup
Run the test script to verify all components:
```bash
python3 test_video_google_api.py
```

### Step 3: Expected Success Output
After setup completion, you should see:
```
🎉 SUCCESS: Google Cloud Video Processing API integration is working!
✅ The video processing pipeline is correctly configured and functional.
```

## 🔄 Testing Process

The test script (`test_video_google_api.py`) performs comprehensive validation:

1. **Environment Check**: Validates all Google Cloud configuration
2. **Credentials Test**: Verifies authentication and permissions
3. **Video Upload**: Tests Cloud Storage integration
4. **AI Analysis**: Tests Vertex AI video processing
5. **Transcription**: Tests Speech-to-Text API
6. **Pipeline Integration**: Validates end-to-end processing

## 🚀 Production Readiness

Once setup is complete, the media processing pipeline provides:

- **Automatic Error Handling**: Robust retry logic for temporary issues
- **Real-time Processing**: Concurrent video analysis and transcription
- **Secure Storage**: Temporary file handling with automatic cleanup
- **Comprehensive Logging**: Detailed processing status and error reporting

## 🔍 Architecture Overview

```
User Upload → VideoProcessor → {
    ├── Cloud Storage (temp upload)
    ├── Vertex AI (video analysis) 
    ├── Speech-to-Text (transcription)
    └── VideoInsight (structured results)
}
```

## 📝 Technical Notes

### Enhanced Retry Logic
The system now includes sophisticated retry handling:
- **Vertex AI Provisioning**: Up to 5 attempts with exponential backoff (10s to 5 minutes)
- **API Rate Limits**: Automatic retry with appropriate delays
- **Transient Errors**: Graceful handling and recovery

### Security Considerations
- Service account credentials stored securely
- Temporary file cleanup after processing
- Bucket lifecycle policies for cost optimization

## 🐛 Debugging Information

### Common Issues and Solutions

1. **Service Agents Provisioning**
   - **Symptom**: "Service agents are being provisioned" error
   - **Solution**: Wait 10-15 minutes (one-time setup)
   - **Status**: ✅ Enhanced retry logic implemented

2. **API Not Enabled**
   - **Symptom**: "API has not been used" error
   - **Solution**: Enable required APIs in Google Cloud Console
   - **Status**: ⚠️ Speech-to-Text API needs enabling

3. **Authentication Issues**
   - **Symptom**: Permission denied errors
   - **Solution**: Verify service account permissions
   - **Status**: ✅ Working correctly

## 📊 Validation Results

The debugging process confirmed:
- ✅ Code structure is correct (no missing await keywords or data fields)
- ✅ Environment configuration is properly loaded
- ✅ Google Cloud integration is functional
- ✅ Error handling is robust and informative
- ⚠️ Only missing: Speech-to-Text API enablement (1-click setup)

---

*Last Updated: January 4, 2025*  
*Debugging Status: Issues identified and resolved*