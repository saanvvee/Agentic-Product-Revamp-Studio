import pytest

from revamp.settings import settings


@pytest.fixture(autouse=True)
def isolated_runs_dir(tmp_path):
    """Tests must not write logs, reports or artifacts into the real runs/ folder.
    Settings is a frozen dataclass shared by reference, so patch the one instance."""
    original = settings.runs_dir
    object.__setattr__(settings, "runs_dir", tmp_path / "runs")
    yield
    object.__setattr__(settings, "runs_dir", original)
