import os
import subprocess
import sys
import tempfile
import unittest
import importlib.util
import importlib.machinery
import json
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

    def load_module(self):
        loader = importlib.machinery.SourceFileLoader("voxpress_postprocess_preview", str(SCRIPT))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_preview_was_edited_ignores_only_trailing_output_newline(self):
        module = self.load_module()
        self.assertFalse(module.preview_was_edited("hello", "hello\n"))
        self.assertTrue(module.preview_was_edited("hello", "hello world"))

    def test_convert_t2s_falls_back_to_external_opencc_python(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_python = Path(tmpdir) / "fake-python"
            fake_python.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "sys.stdin.read()\n"
                "sys.stdout.write('转换后')\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            previous_python = os.environ.get("VOXPRESS_OPENCC_PYTHON")
            previous_opencc = module.OpenCC
            os.environ["VOXPRESS_OPENCC_PYTHON"] = str(fake_python)
            module.OpenCC = None
            try:
                self.assertEqual(module.convert_t2s("轉換前"), "转换后")
            finally:
                module.OpenCC = previous_opencc
                if previous_python is None:
                    os.environ.pop("VOXPRESS_OPENCC_PYTHON", None)
                else:
                    os.environ["VOXPRESS_OPENCC_PYTHON"] = previous_python

    def test_postprocess_invokes_store_for_edited_audio_sample(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime = Path(runtime_dir)
            state_dir = runtime / "voxtype"
            state_dir.mkdir()
            (state_dir / "target_window").write_text("123\n", encoding="utf-8")
            audio_path = runtime / "clip.wav"
            audio_path.write_bytes(b"RIFF\0")
            payload_path = runtime / "payload.json"
            popup_log_path = runtime / "popup.log"
            popup_path = runtime / "fake-popup"
            store_path = runtime / "fake-store"

            popup_path.write_text(
                "#!/usr/bin/env python3\n"
                "import pathlib, sys\n"
                f"pathlib.Path({str(popup_log_path)!r}).open('a', encoding='utf-8').write(' '.join(sys.argv[1:]) + '\\n')\n"
                "if len(sys.argv) > 1 and sys.argv[1] == 'preview':\n"
                "    sys.stdin.read()\n"
                "    sys.stdout.write('测试 corrected')\n",
                encoding="utf-8",
            )
            store_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                f"pathlib.Path({str(payload_path)!r}).write_text(sys.stdin.read(), encoding='utf-8')\n"
                "print(json.dumps({'saved': True, 'id': 'sample'}))\n",
                encoding="utf-8",
            )
            popup_path.chmod(0o755)
            store_path.chmod(0o755)

            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = runtime_dir
            env["DISPLAY"] = ":test"
            env["VOXTYPE_POPUP_UI"] = str(popup_path)
            env["VOXPRESS_CORRECTION_STORE"] = str(store_path)
            env["VOXTYPE_AUDIO_PATH"] = str(audio_path)
            env["VOXTYPE_APPEND_NEWLINE"] = "0"

            result = subprocess.run(
                [sys.executable, str(SCRIPT)],
                input="測試",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "测试 corrected")
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["audio_path"], str(audio_path))
            self.assertEqual(payload["raw_text"], "測試")
            self.assertEqual(payload["preview_text"], "测试")
            self.assertEqual(payload["corrected_text"], "测试 corrected")
            popup_log = popup_log_path.read_text(encoding="utf-8").splitlines()
            self.assertTrue(any(line.startswith("preview") for line in popup_log))
            self.assertFalse(any(line.startswith("saved-correction") for line in popup_log))
            self.assertEqual(
                (state_dir / "saved_correction_pending").read_text(encoding="utf-8"),
                "123",
            )

    def test_postprocess_consumes_pending_audio_file_and_removes_unchanged_audio(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime = Path(runtime_dir)
            state_dir = runtime / "voxtype"
            state_dir.mkdir()
            audio_path = runtime / "pending.wav"
            audio_path.write_bytes(b"RIFF\0")
            (state_dir / "correction_audio_path").write_text(str(audio_path), encoding="utf-8")
            popup_path = runtime / "fake-popup"
            popup_path.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "sys.stdout.write(sys.stdin.read())\n",
                encoding="utf-8",
            )
            popup_path.chmod(0o755)

            env = os.environ.copy()
            env["XDG_RUNTIME_DIR"] = runtime_dir
            env["DISPLAY"] = ":test"
            env["VOXTYPE_POPUP_UI"] = str(popup_path)
            env["VOXTYPE_APPEND_NEWLINE"] = "0"

            result = subprocess.run(
                [sys.executable, str(SCRIPT)],
                input="測試",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "测试")
            self.assertFalse(audio_path.exists())
            self.assertFalse((state_dir / "correction_audio_path").exists())


if __name__ == "__main__":
    unittest.main()
