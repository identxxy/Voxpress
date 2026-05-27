import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-postprocess-preview"


class VoxpressPostprocessTest(unittest.TestCase):
    def run_postprocess(self, text, append_newline):
        with tempfile.TemporaryDirectory() as runtime_dir:
            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = runtime_dir
            env["VOXTYPE_PREVIEW"] = "0"
            env["VOXTYPE_APPEND_NEWLINE"] = "1" if append_newline else "0"
            result = subprocess.run(
                [sys.executable, str(SCRIPT)],
                input=text,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_append_newline_when_enabled(self):
        self.assertEqual(self.run_postprocess("測試", True), "测试\n")

    def test_do_not_append_newline_when_disabled(self):
        self.assertEqual(self.run_postprocess("測試", False), "测试")


if __name__ == "__main__":
    unittest.main()
