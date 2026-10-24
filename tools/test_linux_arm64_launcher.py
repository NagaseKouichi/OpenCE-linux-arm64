"""Portable runtime launcher contracts; no cross compiler or game data needed."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "port/linux_arm64/Halo"

class LauncherTests(unittest.TestCase):
    def test_launcher_passes_arguments_and_keeps_data_environment(self):
        self.assertTrue(LAUNCHER.is_file(), "Linux ARM64 launcher missing")
        with tempfile.TemporaryDirectory(prefix="halo-launch-", dir=ROOT / "build") as tmp:
            root = Path(tmp)
            shutil.copyfile(LAUNCHER, root / "Halo")
            (root / "halo_guest.elf").touch()
            (root / "halo-host").write_text(
                '#!/bin/sh\nprintf "%s\\n" "$HALO_DATA_ROOT" "$1" "$2"\n', encoding="utf-8"
            )
            (root / "halo-host").chmod(0o755)
            result = subprocess.run(["sh", str(root / "Halo"), "--preflight", "argument with spaces"],
                                    env={**os.environ, "HALO_DATA_ROOT": "/my game data"},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["/my game data", "--preflight", "argument with spaces"])

    def test_launcher_rejects_absent_guest_instead_of_claiming_success(self):
        self.assertTrue(LAUNCHER.is_file(), "Linux ARM64 launcher missing")
        with tempfile.TemporaryDirectory(prefix="halo-launch-", dir=ROOT / "build") as tmp:
            root = Path(tmp)
            shutil.copyfile(LAUNCHER, root / "Halo")
            (root / "halo-host").write_text('#!/bin/sh\nexit 0\n', encoding="utf-8")
            (root / "halo-host").chmod(0o755)
            result = subprocess.run(["sh", str(root / "Halo")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("halo_guest.elf", result.stderr)

if __name__ == "__main__":
    (ROOT / "build").mkdir(exist_ok=True)
    unittest.main()
