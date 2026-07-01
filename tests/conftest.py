"""Shared pytest fixtures."""

import sys
import os

# Add shared and service paths so tests can import without Docker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "robot-simulator"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "state-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "ai-service"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "command-api"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "telemetry-ingestion"))
