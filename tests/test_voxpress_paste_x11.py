import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-paste-x11"


class VoxpressPasteX11Test(unittest.TestCase):
    def test_saved_correction_marker_is_shown_after_paste_cleanup(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime = Path(runtime_dir)
            state_dir = runtime / "voxtype"
            state_dir.mkdir()
            marker = state_dir / "saved_correction_pending"
            marker.write_text("123", encoding="utf-8")
            popup_log = runtime / "popup.log"
            popup = runtime / "fake-popup"
            popup.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                f"pathlib.Path({str(popup_log)!r}).open('a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n",
                encoding="utf-8",
            )
            popup.chmod(0o755)

            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = runtime_dir
            env["VOXTYPE_POPUP_UI"] = str(popup)
            env["VOXTYPE_PASTE_DELAY"] = "0"

            result = subprocess.run(
                [str(SCRIPT)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(
                popup_log.read_text(encoding="utf-8").splitlines(),
                ["hide", "saved-correction --reference-window 123"],
            )


if __name__ == "__main__":
    unittest.main()
