# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Keep the additional tests offline and runnable from a source checkout."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("unit tests must not make network requests")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_request)
