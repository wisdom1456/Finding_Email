# Media Processing Guide

This document provides a detailed guide to the audio and video processing capabilities of the Legal Document Analysis Portal.

## Overview

The portal now supports the analysis of audio and video files, extracting valuable insights that are integrated into the final findings letter. This enhancement allows for a more comprehensive case analysis by incorporating evidence from multimedia sources.

## Audio Processing

Audio files are transcribed using OpenAI's Whisper model to generate a searchable text transcript.

### Supported Formats
- MP3
- WAV
- M4A

### Size Limits
- The maximum file size for audio uploads is 25 MB.

### Workflow
1. **Upload**: Audio files are uploaded alongside other case documents.
2. **Transcription**: The `audio_processor.py` module uses OpenAI's Whisper API to transcribe the audio file.
3. **Integration**: The transcript is included in the AI analysis and referenced in the findings letter.

## Video Processing

Video files are analyzed using Google Cloud Video Intelligence API to identify key entities, topics, and provide a scene-by-scene analysis.

### Supported Formats
- MP4
- MOV
- AVI

### Size Limits
- The maximum file size for video uploads is 200 MB.

### Workflow
1. **Upload**: Video files are uploaded to a temporary Google Cloud Storage bucket.
2. **Analysis**: The `video_processor.py` module sends the video to the Google Cloud Video Intelligence API for analysis.
3. **Integration**: Key insights, such as identified objects, text on screen, and scene descriptions, are integrated into the final case analysis.
4. **Cleanup**: The temporary video file is deleted from the Cloud Storage bucket after analysis, following a 24-hour lifecycle policy.

## User Guide

### Uploading Media Files
- Upload audio and video files in the "File Upload" tab along with other documents.
- The system will automatically detect the file type and route it to the appropriate processing service.

### Media Insights in Findings Letters
- **Audio**: Transcripts will be summarized and key quotes may be included in the findings letter.
- **Video**: Significant visual elements, objects, and text identified in the video will be summarized in the "Evidence" section of the findings letter.

### Troubleshooting
- **Upload Failures**: Ensure your file format is supported and within the size limits.
- **Processing Delays**: Video analysis can be time-consuming. Please allow extra time for cases with large video files.
- **Authentication Errors**: Ensure your Google Cloud credentials are correctly configured in the `.env` file.