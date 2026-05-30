import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-pause-listener"


def load_listener(runtime_dir, capture_cmd):
    os.environ["XDG_RUNTIME_DIR"] = str(runtime_dir)
    os.environ["VOXPRESS_AUDIO_CAPTURE_CMD"] = capture_cmd
    os.environ["VOXPRESS_CORRECTION_COLLECTION"] = "1"
    loader = importlib.machinery.SourceFileLoader("voxpress_pause_listener_test", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VoxpressListenerAudioTest(unittest.TestCase):
    def test_audio_capture_writes_pending_path_on_keep(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Path(tmpdir)
            fake_capture = runtime / "fake_capture.py"
            fake_capture.write_text(
                textwrap.dedent(
                    """
                    import pathlib
                    import sys
                    import time

                    path = pathlib.Path(sys.argv[1])
                    path.write_bytes(b"RIFF" + b"0" * 256)
                    while True:
                        time.sleep(0.1)
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            capture_cmd = f"{sys.executable} {fake_capture} {{path}}"
            listener = load_listener(runtime, capture_cmd)

            self.assertTrue(listener.start_correction_audio_capture())
            time.sleep(0.2)
            listener.stop_correction_audio_capture(keep=True)

            audio_path = Path(listener.CORRECTION_AUDIO_FILE).read_text(encoding="utf-8").strip()
            self.assertTrue(Path(audio_path).exists())
            self.assertGreater(Path(audio_path).stat().st_size, 44)
            duration = float(Path(listener.CORRECTION_AUDIO_DURATION_FILE).read_text().strip())
            self.assertGreater(duration, 0)

    def test_audio_capture_cancel_removes_temp_audio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Path(tmpdir)
            fake_capture = runtime / "fake_capture.py"
            fake_capture.write_text(
                "import pathlib, sys, time\n"
                "pathlib.Path(sys.argv[1]).write_bytes(b'RIFF' + b'0' * 256)\n"
                "time.sleep(10)\n",
                encoding="utf-8",
            )
            listener = load_listener(runtime, f"{sys.executable} {fake_capture} {{path}}")

            self.assertTrue(listener.start_correction_audio_capture())
            time.sleep(0.2)
            path = Path(listener.audio_capture_path)
            listener.stop_correction_audio_capture(keep=False)

            self.assertFalse(path.exists())
            self.assertFalse(Path(listener.CORRECTION_AUDIO_FILE).exists())


if __name__ == "__main__":
    unittest.main()
