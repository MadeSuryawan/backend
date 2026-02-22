# tests/conftest.py
"""Root pytest configuration and shared fixtures."""

import os

# Ensure test host is included in trusted hosts for all tests
# This must happen before app is imported anywhere
_TEST_TRUSTED_HOSTS = "localhost,127.0.0.1,0.0.0.0,host.docker.internal,testserver,test"
os.environ["TRUSTED_HOSTS"] = _TEST_TRUSTED_HOSTS
