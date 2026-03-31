import os
import pytest

# Set test secret before any imports
os.environ.setdefault("TRACEVAULT_SECRET", "test-secret")


@pytest.fixture
def test_secret():
    return "test-secret"
