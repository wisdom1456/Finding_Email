#!/usr/bin/env python3
"""
Standalone test script to verify Google Cloud API integration for video processing.

This script tests the video processing pipeline with actual .MOV files from the
Clifton Price case samples and verifies Google Cloud Vertex AI integration.

Prerequisites:
1. Set environment variables:
   - GCP_PROJECT_ID: Your Google Cloud Project ID
   - GCP_BUCKET_NAME: Your Google Cloud Storage bucket name
   - GOOGLE_APPLICATION_CREDENTIALS: Path to your service account JSON file (optional)

2. Ensure Google Cloud authentication is set up (gcloud auth login or service account)

Usage:
    python test_video_google_api.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Load environment variables from .env file
load_dotenv()

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

from backend.utils.data_models import MediaProcessingError, VideoInsight
from backend_logic.video_processor import VideoProcessor


def check_environment():
    """Check if the environment is properly configured for Google Cloud API access."""
logger.debug('🔍 Checking Google Cloud configuration...')

    from backend_logic.config import get_settings

    settings = get_settings()

    project_id = settings.gcp_project_id
    bucket_name = settings.gcp_bucket_name
    credentials_file = settings.google_application_credentials

logger.info(f'📋 Project ID: {project_id or 'NOT SET'}')
logger.info(f'🪣 Bucket Name: {bucket_name or 'NOT SET'}')
logger.info(f'🔑 Credentials File: {credentials_file or 'Using default authentication'}')

    if not project_id:
logger.error('❌ ERROR: GCP_PROJECT_ID environment variable is required')
logger.info("   Set it with: export GCP_PROJECT_ID='your-project-id'")
        return False

    if not bucket_name:
logger.error('❌ ERROR: GCP_BUCKET_NAME environment variable is required')
logger.info("   Set it with: export GCP_BUCKET_NAME='your-bucket-name'")
        return False

    if credentials_file:
        if not os.path.exists(credentials_file):
logger.error(f'❌ ERROR: Credentials file not found: {credentials_file}')
            return False
logger.info('✅ Credentials file exists and is accessible')
    else:
logger.info('⚠️  Using default authentication (gcloud auth login)')

logger.info('✅ Environment configuration looks good!')
    return True


def find_sample_videos():
    """Find available video files in the Price case samples."""
    video_dir = (
        project_root
        / "samples"
        / "Price, Clifton [MetLife]"
        / "Shared Folder with Client"
        / "Shared with Bernhardt Riley"
        / "2024 Pictures Videos"
    )

    if not video_dir.exists():
logger.error(f'❌ ERROR: Sample video directory not found: {video_dir}')
        return []

    video_files = list(video_dir.glob("*.MOV"))

    if not video_files:
logger.error(f'❌ ERROR: No .MOV files found in: {video_dir}')
        return []

logger.info(f'📹 Found {len(video_files)} video files:')
    for video_file in video_files:
        size_mb = video_file.stat().st_size / (1024 * 1024)
logger.info(f'   - {video_file.name} ({size_mb:.2f} MB)')

    return video_files


async def test_video_processor_initialization():
    """Test that VideoProcessor can be initialized with Google Cloud credentials."""
logger.info('\n🔧 Testing VideoProcessor initialization...')

    try:
        processor = VideoProcessor()
logger.info('✅ VideoProcessor initialized successfully')
logger.info(f'📋 Project ID: {processor.project_id}')
logger.info(f'🪣 Bucket Name: {processor.bucket_name}')
        return processor
    except Exception as e:
logger.error(f'❌ ERROR: Failed to initialize VideoProcessor: {e}')
        return None


async def test_single_video_processing(processor, video_file):
    """Test processing a single video file with the Google Cloud API."""
logger.debug(f'\n🎥 Testing video processing with: {video_file.name}')

    file_size_mb = video_file.stat().st_size / (1024 * 1024)
logger.info(f'📏 File size: {file_size_mb:.2f} MB')

    try:
        # Process the video file
logger.debug('🚀 Starting video processing...')
        result = await processor.process_video_file(
            file_path=str(video_file), file_name=video_file.name
        )

        if isinstance(result, VideoInsight):
logger.debug('✅ Video processing completed successfully!')

            # Display results
logger.debug(f'\n📊 Processing Results for {result.file_name}:')
logger.info(f'   🧠 Analysis insights: {list(result.insights.keys())}')

            if result.transcript:
                transcript_preview = (
                    result.transcript[:200] + "..."
                    if len(result.transcript) > 200
                    else result.transcript
                )
logger.info(f'   🎤 Transcript: {transcript_preview}')
            else:
logger.info('   🎤 No transcript generated')

            if result.labels:
logger.info(f'   🏷️  Labels detected: {len(result.labels)} items')
logger.info(f'   🏷️  Sample labels: {result.labels[:3]}')

            if result.objects:
logger.info(f'   🎯 Objects detected: {len(result.objects)} items')
logger.info(f'   🎯 Sample objects: {result.objects[:3]}')

            # Check Vertex AI analysis
            vertex_analysis = result.insights.get("vertex_analysis", {})
            if vertex_analysis:
logger.info(f'   🤖 Vertex AI analysis: {list(vertex_analysis.keys())}')
            else:
logger.info('   🤖 No Vertex AI analysis results')

            return True

        if isinstance(result, MediaProcessingError):
logger.error('⚠️  Video processing failed gracefully:')
logger.error(f'   📝 Error: {result.error_message}')
logger.error(f'   🔧 Type: {result.error_type}')
logger.info(f'   📍 Source: {result.source}')
            return False

logger.info(f'❌ Unexpected result type: {type(result)}')
        return False

    except Exception as e:
logger.error(f'❌ ERROR: Video processing failed with exception: {e}')
        return False


async def main():
    """Main test execution function."""
logger.debug('🎬 Google Cloud Video Processing API Test')
logger.info('=' * 50)

    # Step 1: Check environment configuration
    if not check_environment():
logger.error('\n❌ Environment configuration failed. Please fix the issues above.')
        return False

    # Step 2: Find sample video files
    video_files = find_sample_videos()
    if not video_files:
logger.info('\n❌ No sample video files found. Cannot proceed with testing.')
        return False

    # Step 3: Initialize VideoProcessor
    processor = await test_video_processor_initialization()
    if not processor:
logger.error('\n❌ VideoProcessor initialization failed. Cannot proceed with testing.')
        return False

    # Step 4: Test with the smallest video file first
    smallest_video = min(video_files, key=lambda f: f.stat().st_size)
logger.info(f'\n🎯 Testing with smallest video file: {smallest_video.name}')

    success = await test_single_video_processing(processor, smallest_video)

    if success:
logger.debug('\n🎉 SUCCESS: Google Cloud Video Processing API integration is working!')
logger.info('✅ The video processing pipeline is correctly configured and functional.')
            "✅ The video processing pipeline is correctly configured and functional."
        )

        # Optionally test one more file if available
        if len(video_files) > 1:
logger.info('\n🔄 Testing with one additional file...')
            second_video = (
                video_files[1] if video_files[1] != smallest_video else video_files[0]
            )
            await test_single_video_processing(processor, second_video)

    else:
logger.error('\n❌ FAILURE: Google Cloud Video Processing API integration has issues.')
logger.info('🔧 Please check your Google Cloud configuration and try again.')

    return success


if __name__ == "__main__":
logger.debug('Starting Google Cloud Video Processing API test...')
logger.info('Please ensure your Google Cloud credentials are properly configured.\n')

    try:
        result = asyncio.run(main())
        exit_code = 0 if result else 1
logger.error(f'\nTest {('PASSED' if result else 'FAILED')}')
        sys.exit(exit_code)
    except KeyboardInterrupt:
logger.info('\n🛑 Test interrupted by user')
        sys.exit(1)
    except Exception as e:
logger.error(f'\n💥 Unexpected error during testing: {e}')
        sys.exit(1)
