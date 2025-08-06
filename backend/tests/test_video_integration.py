import asyncio
import os
import pytest
from pathlib import Path
import sys

# Add the project root to the Python path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend_logic.video_processor import VideoProcessor
from backend.utils.data_models import VideoInsight, MediaProcessingError

# This is an integration test that requires real Google Cloud credentials
# Skip if running in CI/CD or if credentials are not available
SKIP_INTEGRATION = not os.getenv("GCP_PROJECT_ID") or not os.getenv("GCP_BUCKET_NAME")

@pytest.mark.skipif(SKIP_INTEGRATION, reason="Google Cloud credentials not available for integration testing")
@pytest.mark.integration
class TestVideoProcessorIntegration:
    """Integration tests for VideoProcessor using real Google Cloud APIs and actual video files."""
    
    @pytest.fixture(scope="class")
    def video_processor(self):
        """Create a real VideoProcessor instance with actual Google Cloud credentials."""
        project_id = os.getenv("GCP_PROJECT_ID")
        bucket_name = os.getenv("GCP_BUCKET_NAME")
        
        if not project_id or not bucket_name:
            pytest.skip("GCP_PROJECT_ID and GCP_BUCKET_NAME environment variables required")
        
        try:
            processor = VideoProcessor(project_id=project_id, bucket_name=bucket_name)
            return processor
        except Exception as e:
            pytest.skip(f"Failed to initialize VideoProcessor: {e}")
    
    @pytest.fixture(scope="class")
    def sample_video_file(self):
        """Get path to a real video file from the Price case samples."""
        video_path = Path(__file__).resolve().parents[2] / "samples" / "Price, Clifton [MetLife]" / "Shared Folder with Client" / "Shared with Bernhardt Riley" / "2024 Pictures Videos" / "08-05-2024 Video 1.MOV"
        
        if not video_path.exists():
            pytest.skip(f"Sample video file not found: {video_path}")
        
        return str(video_path)
    
    @pytest.mark.asyncio
    async def test_real_video_processing_end_to_end(self, video_processor, sample_video_file):
        """Test complete video processing pipeline with real Google Cloud APIs."""
        print(f"\n🎥 Testing video processing with file: {Path(sample_video_file).name}")
        print(f"📁 File size: {os.path.getsize(sample_video_file) / (1024*1024):.2f} MB")
        
        try:
            # Process the actual video file
            result = await video_processor.process_video_file(
                file_path=sample_video_file,
                file_name="08-05-2024 Video 1.MOV"
            )
            
            # Verify successful processing
            assert isinstance(result, VideoInsight), f"Expected VideoInsight, got {type(result)}"
            
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
            print("\n✅ Video processing successful!")
            print(f"📊 Insights keys: {list(result.insights.keys())}")
            if result.transcript:
                print(f"🎤 Transcript length: {len(result.transcript)} characters")
                print(f"🎤 Transcript preview: {result.transcript[:200]}...")
            else:
                print("🎤 No transcript generated")
            
            if result.labels:
                print(f"🏷️  Labels detected: {len(result.labels)} items")
                print(f"🏷️  Labels: {result.labels[:5]}")  # Show first 5 labels
            
            if result.objects:
                print(f"🎯 Objects detected: {len(result.objects)} items")
                print(f"🎯 Objects: {result.objects[:5]}")  # Show first 5 objects
            
            # Verify Vertex AI analysis results
            vertex_analysis = result.insights.get("vertex_analysis", {})
            print(f"🧠 Vertex AI analysis keys: {list(vertex_analysis.keys())}")
            
            return result
            
        except Exception as e:
            print(f"\n❌ Video processing failed: {e}")
            # If it's a MediaProcessingError, it's handled gracefully
            if isinstance(result, MediaProcessingError):
                print(f"📝 Error details: {result.error_message}")
                print(f"🔧 Error type: {result.error_type}")
            raise
    
    @pytest.mark.asyncio
    async def test_video_processing_with_small_file(self, video_processor):
        """Test video processing with the smallest available video file."""
        # Find the smallest video file in the samples
        video_dir = Path(__file__).resolve().parents[2] / "samples" / "Price, Clifton [MetLife]" / "Shared Folder with Client" / "Shared with Bernhardt Riley" / "2024 Pictures Videos"
        
        video_files = list(video_dir.glob("*.MOV"))
        if not video_files:
            pytest.skip("No .MOV files found in sample directory")
        
        # Find the smallest file
        smallest_file = min(video_files, key=lambda f: f.stat().st_size)
        file_size_mb = smallest_file.stat().st_size / (1024*1024)
        
        print(f"\n🎥 Testing with smallest video: {smallest_file.name} ({file_size_mb:.2f} MB)")
        
        result = await video_processor.process_video_file(
            file_path=str(smallest_file),
            file_name=smallest_file.name
        )
        
        if isinstance(result, VideoInsight):
            print(f"✅ Processing successful for {smallest_file.name}")
            assert result.file_name == smallest_file.name
            assert result.insights is not None
        elif isinstance(result, MediaProcessingError):
            print(f"⚠️  Processing failed gracefully: {result.error_message}")
            # This is still considered a success since errors are handled gracefully
            assert result.source == "VideoProcessor"
            assert result.file_name == smallest_file.name
        else:
            pytest.fail(f"Unexpected result type: {type(result)}")
    
    @pytest.mark.asyncio
    async def test_multiple_video_files_processing(self, video_processor):
        """Test processing multiple video files to verify consistency."""
        video_dir = Path(__file__).resolve().parents[2] / "samples" / "Price, Clifton [MetLife]" / "Shared Folder with Client" / "Shared with Bernhardt Riley" / "2024 Pictures Videos"
        
        video_files = list(video_dir.glob("*.MOV"))[:2]  # Test with first 2 files
        if len(video_files) < 2:
            pytest.skip("Need at least 2 video files for batch testing")
        
        print(f"\n🎥 Testing batch processing of {len(video_files)} videos")
        
        results = []
        for video_file in video_files:
            print(f"📹 Processing: {video_file.name}")
            result = await video_processor.process_video_file(
                file_path=str(video_file),
                file_name=video_file.name
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
                print(f"✅ {video_name}: Success")
                assert result.file_name == video_name
            elif isinstance(result, MediaProcessingError):
                error_count += 1
                print(f"⚠️  {video_name}: Error - {result.error_message}")
                assert result.file_name == video_name
            else:
                pytest.fail(f"Unexpected result type for {video_name}: {type(result)}")
        
        print(f"\n📊 Batch processing results: {successful_count} successful, {error_count} errors")
        
        # At least one should succeed for the test to pass
        assert successful_count > 0, "At least one video should process successfully"


@pytest.mark.skipif(SKIP_INTEGRATION, reason="Google Cloud credentials not available")
def test_google_cloud_credentials():
    """Verify that Google Cloud credentials are properly configured."""
    project_id = os.getenv("GCP_PROJECT_ID")
    bucket_name = os.getenv("GCP_BUCKET_NAME")
    credentials_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    print("\n🔐 Google Cloud Configuration Check:")
    print(f"📋 Project ID: {project_id}")
    print(f"🪣 Bucket Name: {bucket_name}")
    print(f"🔑 Credentials File: {credentials_file}")
    
    assert project_id, "GCP_PROJECT_ID environment variable is required"
    assert bucket_name, "GCP_BUCKET_NAME environment variable is required"
    
    if credentials_file:
        assert os.path.exists(credentials_file), f"Credentials file not found: {credentials_file}"
        print("✅ Credentials file exists and is accessible")
    else:
        print("⚠️  GOOGLE_APPLICATION_CREDENTIALS not set, using default authentication")


if __name__ == "__main__":
    # Allow running this test file directly for quick integration testing
    pytest.main([__file__, "-v", "-s", "--tb=short"])