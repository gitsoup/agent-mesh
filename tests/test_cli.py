import subprocess
import sys
from pathlib import Path

def test_version_command_prints_package_version() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "agent_mesh", "version"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "0.1.0" in result.stdout
