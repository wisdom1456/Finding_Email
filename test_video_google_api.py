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


# Load environment variables from .env file
load_dotenv()

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

from backend.utils.data_models import MediaProcessingError, VideoInsight
from backend_logic.video_processor import VideoProcessor


def check_environment():
    """Check if the environment is properly configured for Google Cloud API access."""
    print("🔍 Checking Google Cloud configuration...")

    from backend_logic.config import get_settings

    settings = get_settings()

    project_id = settings.gcp_project_id
    bucket_name = settings.gcp_bucket_name
    credentials_file = settings.google_application_credentials

    print(f"📋 Project ID: {project_id or 'NOT SET'}")
    print(f"🪣 Bucket Name: {bucket_name or 'NOT SET'}")
    print(f"🔑 Credentials File: {credentials_file or 'Using default authentication'}")

    if not project_id:
        print("❌ ERROR: GCP_PROJECT_ID environment variable is required")
        print("   Set it with: export GCP_PROJECT_ID='your-project-id'")
        return False

    if not bucket_name:
        print("❌ ERROR: GCP_BUCKET_NAME environment variable is required")
        print("   Set it with: export GCP_BUCKET_NAME='your-bucket-name'")
        return False

    if credentials_file:
        if not os.path.exists(credentials_file):
            print(f"❌ ERROR: Credentials file not found: {credentials_file}")
            return False
        print("✅ Credentials file exists and is accessible")
    else:
        print("⚠️  Using default authentication (gcloud auth login)")

    print("✅ Environment configuration looks good!")
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
        print(f"❌ ERROR: Sample video directory not found: {video_dir}")
        return []

    video_files = list(video_dir.glob("*.MOV"))

    if not video_files:
        print(f"❌ ERROR: No .MOV files found in: {video_dir}")
        return []

    print(f"📹 Found {len(video_files)} video files:")
    for video_file in video_files:
        size_mb = video_file.stat().st_size / (1024 * 1024)
        print(f"   - {video_file.name} ({size_mb:.2f} MB)")

    return video_files


async def test_video_processor_initialization():
    """Test that VideoProcessor can be initialized with Google Cloud credentials."""
    print("\n🔧 Testing VideoProcessor initialization...")

    try:
        processor = VideoProcessor()
        print("✅ VideoProcessor initialized successfully")
        print(f"📋 Project ID: {processor.project_id}")
        print(f"🪣 Bucket Name: {processor.bucket_name}")
        return processor
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize VideoProcessor: {e}")
        return None


async def test_single_video_processing(processor, video_file):
    """Test processing a single video file with the Google Cloud API."""
    print(f"\n🎥 Testing video processing with: {video_file.name}")

    file_size_mb = video_file.stat().st_size / (1024 * 1024)
    print(f"📏 File size: {file_size_mb:.2f} MB")

    try:
        # Process the video file
        print("🚀 Starting video processing...")
        result = await processor.process_video_file(
            file_path=str(video_file), file_name=video_file.name
        )

        if isinstance(result, VideoInsight):
            print("✅ Video processing completed successfully!")

            # Display results
            print(f"\n📊 Processing Results for {result.file_name}:")
            print(f"   🧠 Analysis insights: {list(result.insights.keys())}")

            if result.transcript:
                transcript_preview = (
                    result.transcript[:200] + "..."
                    if len(result.transcript) > 200
                    else result.transcript
                )
                print(f"   🎤 Transcript: {transcript_preview}")
            else:
                print("   🎤 No transcript generated")

            if result.labels:
                print(f"   🏷️  Labels detected: {len(result.labels)} items")
                print(f"   🏷️  Sample labels: {result.labels[:3]}")

            if result.objects:
                print(f"   🎯 Objects detected: {len(result.objects)} items")
                print(f"   🎯 Sample objects: {result.objects[:3]}")

            # Check Vertex AI analysis
            vertex_analysis = result.insights.get("vertex_analysis", {})
            if vertex_analysis:
                print(f"   🤖 Vertex AI analysis: {list(vertex_analysis.keys())}")
            else:
                print("   🤖 No Vertex AI analysis results")

            return True

        if isinstance(result, MediaProcessingError):
            print("⚠️  Video processing failed gracefully:")
            print(f"   📝 Error: {result.error_message}")
            print(f"   🔧 Type: {result.error_type}")
            print(f"   📍 Source: {result.source}")
            return False

        print(f"❌ Unexpected result type: {type(result)}")
        return False

    except Exception as e:
        print(f"❌ ERROR: Video processing failed with exception: {e}")
        return False


async def main():
    """Main test execution function."""
    print("🎬 Google Cloud Video Processing API Test")
    print("=" * 50)

    # Step 1: Check environment configuration
    if not check_environment():
        print("\n❌ Environment configuration failed. Please fix the issues above.")
        return False

    # Step 2: Find sample video files
    video_files = find_sample_videos()
    if not video_files:
        print("\n❌ No sample video files found. Cannot proceed with testing.")
        return False

    # Step 3: Initialize VideoProcessor
    processor = await test_video_processor_initialization()
    if not processor:
        print("\n❌ VideoProcessor initialization failed. Cannot proceed with testing.")
        return False

    # Step 4: Test with the smallest video file first
    smallest_video = min(video_files, key=lambda f: f.stat().st_size)
    print(f"\n🎯 Testing with smallest video file: {smallest_video.name}")

    success = await test_single_video_processing(processor, smallest_video)

    if success:
        print("\n🎉 SUCCESS: Google Cloud Video Processing API integration is working!")
        print(
            "✅ The video processing pipeline is correctly configured and functional."
        )

        # Optionally test one more file if available
        if len(video_files) > 1:
            print("\n🔄 Testing with one additional file...")
            second_video = (
                video_files[1] if video_files[1] != smallest_video else video_files[0]
            )
            await test_single_video_processing(processor, second_video)

    else:
        print("\n❌ FAILURE: Google Cloud Video Processing API integration has issues.")
        print("🔧 Please check your Google Cloud configuration and try again.")

    return success


if __name__ == "__main__":
    print("Starting Google Cloud Video Processing API test...")
    print("Please ensure your Google Cloud credentials are properly configured.\n")

    try:
        result = asyncio.run(main())
        exit_code = 0 if result else 1
        print(f"\nTest {'PASSED' if result else 'FAILED'}")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error during testing: {e}")
        sys.exit(1)
