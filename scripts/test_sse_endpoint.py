#!/usr/bin/env python3
"""Test SSE endpoints manually."""

import asyncio
import sys

from legal_portal.services.progress_manager import ProgressManager


async def test_progress_manager():
    """Test the progress manager."""
    print("=" * 60)
    print("Testing Progress Manager")
    print("=" * 60)
    print()

    # Get singleton instance
    manager = ProgressManager.get_instance()

    # Create a test channel
    test_id = "test-123"
    print(f"Creating channel: {test_id}")
    await manager.create_channel(test_id)
    print("✅ Channel created")
    print()

    # Publish some test events
    print("Publishing test events...")
    await manager.publish_progress(
        channel_id=test_id, message="Test message 1", phase="test_phase", percent=25
    )
    print("  ✓ Event 1 published")

    await manager.publish_progress(
        channel_id=test_id,
        message="Test message 2",
        phase="test_phase",
        percent=50,
        current_doc={"name": "test.pdf", "index": 1, "total": 2},
    )
    print("  ✓ Event 2 published")

    await manager.publish_progress(
        channel_id=test_id, message="Test complete", phase="completed", percent=100, status="completed"
    )
    print("  ✓ Event 3 (completion) published")
    print()

    print("✅ Progress Manager test passed!")
    print()
    print("To test the SSE endpoint:")
    print(f"  curl http://localhost:8000/api/progress/analysis/{test_id}")
    print()
    print("(Note: The events are already consumed, so create a new test)")


if __name__ == "__main__":
    try:
        asyncio.run(test_progress_manager())
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
