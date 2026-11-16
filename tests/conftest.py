from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def journal() -> Path:
    return FIXTURES / "Journal.260101120000.01.log"
