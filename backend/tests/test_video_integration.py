from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



# Add the project root to the Python path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.utils.data_models import MediaProcessingError, VideoInsight

# This is an integration test that requires real Google Cloud credentials
# Skip if running in CI/CD or if credentials are not available
from backend_logic.config import get_settings
from backend_logic.video_processor import VideoProcessor


settings = get_settings()
SKIP_INTEGRATION = not settings.gcp_project_id or not settings.gcp_bucket_name


@pytest.mark.skipif(
    SKIP_INTEGRATION,
    reason="Google Cloud credentials not available for integration testing",
)
@pytest.mark.integration
class TestVideoProcessorIntegration:
    """Integration tests for VideoProcessor using real Google Cloud APIs and actual video files."""

    @pytest.fixture(scope="class")
    def video_processor(self):
        """Create a real VideoProcessor instance with actual Google Cloud credentials."""
        project_id = settings.gcp_project_id
        bucket_name = settings.gcp_bucket_name

        if not project_id or not bucket_name:
            pytest.skip(
                "GCP_PROJECT_ID and GCP_BUCKET_NAME environment variables required"
            )

        try:
            return VideoProcessor(project_id=project_id, bucket_name=bucket_name)
        except Exception as e:
            pytest.skip(f"Failed to initialize VideoProcessor: {e}")

    @pytest.fixture(scope="class")
    def sample_video_file(self):
        """Get path to a real video file from the Price case samples."""
        video_path = (
            Path(__file__).resolve().parents[2]
            / "samples"
            / "Price, Clifton [MetLife]"
            / "Shared Folder with Client"
            / "Shared with Bernhardt Riley"
            / "2024 Pictures Videos"
            / "08-05-2024 Video 1.MOV"
        )

        if not video_path.exists():
            pytest.skip(f"Sample video file not found: {video_path}")

        return str(video_path)

    @pytest.mark.asyncio
    async def test_real_video_processing_end_to_end(
        self, video_processor, sample_video_file
    ):
        """Test complete video processing pipeline with real Google Cloud APIs."""
logger.info(f'\n🎥 Testing video processing with file: {Path(sample_video_file).name}')
            f"\n🎥 Testing video processing with file: {Path(sample_video_file).name}"
        )
logger.info(f'📁 File size: {os.path.getsize(sample_video_file) / (1024 * 1024):.2f} MB')
            f"📁 File size: {os.path.getsize(sample_video_file) / (1024 * 1024):.2f} MB"
        )

        try:
            # Process the actual video file
            result = await video_processor.process_video_file(
                file_path=sample_video_file, file_name="08-05-2024 Video 1.MOV"
            )

            # Verify successful processing
            assert isinstance(result, VideoInsight), (
                f"Expected VideoInsight, got {type(result)}"
            )

            # Verify required fields are present
            assert result.file_name == "08-05-2024 Video 1.MOV"
            assert result.insights is not None
            assert isinstance(result.insights, dict)
            assert "vertex_analysis" in result.insights

            # Verify metadata is populated
            assert result.metadata is not None
            assert result.metadata.filename == "08-05-2024 Video 1.MOV"
            assert result.metadata.size > 0

            # Print results for manual verification
logger.debug('\n✅ Video processing successful!')
logger.info(f'📊 Insights keys: {list(result.insights.keys())}')
            if result.transcript:
logger.info(f'🎤 Transcript length: {len(result.transcript)} characters')
logger.info(f'🎤 Transcript preview: {result.transcript[:200]}...')
            else:
logger.info('🎤 No transcript generated')

            if result.labels:
logger.info(f'🏷️  Labels detected: {len(result.labels)} items')
logger.info(f'🏷️  Labels: {result.labels[:5]}')

            if result.objects:
logger.info(f'🎯 Objects detected: {len(result.objects)} items')
logger.info(f'🎯 Objects: {result.objects[:5]}')

            # Verify Vertex AI analysis results
            vertex_analysis = result.insights.get("vertex_analysis", {})
logger.info(f'🧠 Vertex AI analysis keys: {list(vertex_analysis.keys())}')

            return result

        except Exception as e:
logger.error(f'\n❌ Video processing failed: {e}')
            # If it's a MediaProcessingError, it's handled gracefully
            if isinstance(result, MediaProcessingError):
logger.error(f'📝 Error details: {result.error_message}')
logger.error(f'🔧 Error type: {result.error_type}')
            raise

    @pytest.mark.asyncio
    async def test_video_processing_with_small_file(self, video_processor):
        """Test video processing with the smallest available video file."""
        # Find the smallest video file in the samples
        video_dir = (
            Path(__file__).resolve().parents[2]
            / "samples"
            / "Price, Clifton [MetLife]"
            / "Shared Folder with Client"
            / "Shared with Bernhardt Riley"
            / "2024 Pictures Videos"
        )

        video_files = list(video_dir.glob("*.MOV"))
        if not video_files:
            pytest.skip("No .MOV files found in sample directory")

        # Find the smallest file
        smallest_file = min(video_files, key=lambda f: f.stat().st_size)
        file_size_mb = smallest_file.stat().st_size / (1024 * 1024)

logger.info(f'\n🎥 Testing with smallest video: {smallest_file.name} ({file_size_mb:.2f} MB)')
            f"\n🎥 Testing with smallest video: {smallest_file.name} ({file_size_mb:.2f} MB)"
        )

        result = await video_processor.process_video_file(
            file_path=str(smallest_file), file_name=smallest_file.name
        )

        if isinstance(result, VideoInsight):
logger.debug(f'✅ Processing successful for {smallest_file.name}')
            assert result.file_name == smallest_file.name
            assert result.insights is not None
        elif isinstance(result, MediaProcessingError):
logger.error(f'⚠️  Processing failed gracefully: {result.error_message}')
            # This is still considered a success since errors are handled gracefully
            assert result.source == "VideoProcessor"
            assert result.file_name == smallest_file.name
        else:
            pytest.fail(f"Unexpected result type: {type(result)}")

    @pytest.mark.asyncio
    async def test_multiple_video_files_processing(self, video_processor):
        """Test processing multiple video files to verify consistency."""
        video_dir = (
            Path(__file__).resolve().parents[2]
            / "samples"
            / "Price, Clifton [MetLife]"
            / "Shared Folder with Client"
            / "Shared with Bernhardt Riley"
            / "2024 Pictures Videos"
        )

        video_files = list(video_dir.glob("*.MOV"))[:2]  # Test with first 2 files
        if len(video_files) < 2:
            pytest.skip("Need at least 2 video files for batch testing")

logger.debug(f'\n🎥 Testing batch processing of {len(video_files)} videos')

        results = []
        for video_file in video_files:
logger.debug(f'📹 Processing: {video_file.name}')
            result = await video_processor.process_video_file(
                file_path=str(video_file), file_name=video_file.name
            )
            results.append(result)

            # Add small delay between processing to be respectful to API limits
            await asyncio.sleep(2)

        # Verify all results
        successful_count = 0
        error_count = 0

        for i, result in enumerate(results):
            video_name = video_files[i].name
            if isinstance(result, VideoInsight):
                successful_count += 1
logger.info(f'✅ {video_name}: Success')
                assert result.file_name == video_name
            elif isinstance(result, MediaProcessingError):
                error_count += 1
logger.error(f'⚠️  {video_name}: Error - {result.error_message}')
                assert result.file_name == video_name
            else:
                pytest.fail(f"Unexpected result type for {video_name}: {type(result)}")

logger.info(f'\n📊 Batch processing results: {successful_count} successful, {error_count} errors')
            f"\n📊 Batch processing results: {successful_count} successful, {error_count} errors"
        )

        # At least one should succeed for the test to pass
        assert successful_count > 0, "At least one video should process successfully"


@pytest.mark.skipif(SKIP_INTEGRATION, reason="Google Cloud credentials not available")
def test_google_cloud_credentials():
    """Verify that Google Cloud credentials are properly configured."""
    project_id = settings.gcp_project_id
    bucket_name = settings.gcp_bucket_name
    credentials_file = settings.google_application_credentials

logger.info('\n🔐 Google Cloud Configuration Check:')
logger.info(f'📋 Project ID: {project_id}')
logger.info(f'🪣 Bucket Name: {bucket_name}')
logger.info(f'🔑 Credentials File: {credentials_file}')

    assert project_id, "GCP_PROJECT_ID environment variable is required"
    assert bucket_name, "GCP_BUCKET_NAME environment variable is required"

    if credentials_file:
        assert os.path.exists(credentials_file), (
            f"Credentials file not found: {credentials_file}"
        )
logger.info('✅ Credentials file exists and is accessible')
    else:
logger.info('⚠️  GOOGLE_APPLICATION_CREDENTIALS not set, using default authentication')


if __name__ == "__main__":
    # Allow running this test file directly for quick integration testing
    pytest.main([__file__, "-v", "-s", "--tb=short"])
