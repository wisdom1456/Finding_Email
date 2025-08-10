#!/usr/bin/env python3
"""
Test script for main_processor.py to verify help functionality works.
"""

from __future__ import annotations

import os
import subprocess
import sys
from utils.logging_config import setup_logging
logger = setup_logging('unknown_service')



def test_help():
    """Test that the help command works."""
    try:
        # Set environment variable to skip optional imports during help display
        env = os.environ.copy()
        env["SKIP_OPTIONAL_IMPORTS"] = "1"

        result = subprocess.run(
            [sys.executable, "backend_logic/main_processor.py", "--help"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

logger.info('Return code:' + " " + result.returncode)
logger.info('STDOUT:' + " " + result.stdout)
logger.info('STDERR:' + " " + result.stderr)

        if result.returncode == 0:
logger.info('✅ Help command works!')
            return True
logger.error('❌ Help command failed')
        return False

    except Exception as e:
logger.error(f'❌ Test failed with exception: {e}')
        return False


if __name__ == "__main__":
    success = test_help()
    sys.exit(0 if success else 1)
