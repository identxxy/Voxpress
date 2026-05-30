import json
import os
import runpy
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-export-whisper-deploy"


class VoxpressExportWhisperDeployTest(unittest.TestCase):
    def test_missing_export_tools_reports_not_deployable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            adapter = base / "adapter"
            processor = base / "processor"
            output = base / "deploy"
            adapter.mkdir()
            processor.mkdir()

            env = os.environ.copy()
            for key in (
                "VOXPRESS_WHISPER_EXPORT_COMMAND",
                "VOXPRESS_WHISPER_TOOL_ROOT",
                "VOXPRESS_WHISPER_CPP_CONVERT_SCRIPT",
                "VOXPRESS_OPENAI_WHISPER_REPO",
                "VOXPRESS_WHISPER_CPP_QUANTIZE_BIN",
            ):
                env.pop(key, None)
            env["VOXPRESS_WHISPER_TOOL_ROOT"] = str(base / "missing-tools")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--base-model",
                    "openai/whisper-large-v3-turbo",
                    "--adapter-dir",
                    str(adapter),
                    "--processor-dir",
                    str(processor),
                    "--output-dir",
                    str(output),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "export_unavailable")
            self.assertIsNone(payload["deploy_model_path"])
            self.assertFalse((output / "merged-hf").exists())

    def test_find_bin_candidates_ignores_merged_hf_weights(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            merged = output / "merged-hf"
            merged.mkdir()
            (merged / "pytorch_model.bin").write_bytes(b"x" * 1024)
            ggml = output / "ggml-model.bin"
            ggml.write_bytes(b"ggml")

            namespace = runpy.run_path(str(SCRIPT))
            candidates = namespace["find_bin_candidates"](output)

            self.assertEqual(candidates, [ggml])

    def test_legacy_quantize_binary_is_not_autodetected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            legacy = base / "whisper.cpp" / "build" / "bin" / "quantize"
            marker = base / "legacy-ran"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                f"#!/usr/bin/env bash\nprintf ran > {str(marker)!r}\ntouch \"$2\"\nexit 0\n",
                encoding="utf-8",
            )
            legacy.chmod(0o755)
            output = base / "deploy"
            output.mkdir()

            previous_root = os.environ.get("VOXPRESS_WHISPER_TOOL_ROOT")
            previous_bin = os.environ.get("VOXPRESS_WHISPER_CPP_QUANTIZE_BIN")
            os.environ["VOXPRESS_WHISPER_TOOL_ROOT"] = str(base)
            os.environ.pop("VOXPRESS_WHISPER_CPP_QUANTIZE_BIN", None)
            try:
                namespace = runpy.run_path(str(SCRIPT))
                self.assertIsNone(namespace["maybe_quantize"](base / "ggml-model.bin", output))
                self.assertFalse(marker.exists())
            finally:
                if previous_root is None:
                    os.environ.pop("VOXPRESS_WHISPER_TOOL_ROOT", None)
                else:
                    os.environ["VOXPRESS_WHISPER_TOOL_ROOT"] = previous_root
                if previous_bin is None:
                    os.environ.pop("VOXPRESS_WHISPER_CPP_QUANTIZE_BIN", None)
                else:
                    os.environ["VOXPRESS_WHISPER_CPP_QUANTIZE_BIN"] = previous_bin

    def test_converter_stdout_does_not_pollute_exporter_json_channel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            convert_script = base / "convert.py"
            convert_script.write_text(
                "\n".join(
                    [
                        "import pathlib",
                        "import sys",
                        "print('converter progress log')",
                        "output = pathlib.Path(sys.argv[3])",
                        "output.mkdir(parents=True, exist_ok=True)",
                        "(output / 'ggml-model.bin').write_bytes(b'ggml')",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            whisper_repo = base / "whisper"
            whisper_repo.mkdir()
            output = base / "deploy"

            driver = base / "driver.py"
            driver.write_text(
                textwrap.dedent(
                    f"""
                    import json
                    import pathlib
                    import runpy

                    namespace = runpy.run_path({str(SCRIPT)!r})
                    args = type('Args', (), {{'output_dir': pathlib.Path({str(output)!r})}})()
                    payload = namespace['run_whisper_cpp_export'](args, {str(base / 'merged-hf')!r})
                    print(json.dumps(payload))
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["VOXPRESS_WHISPER_CPP_CONVERT_SCRIPT"] = str(convert_script)
            env["VOXPRESS_OPENAI_WHISPER_REPO"] = str(whisper_repo)
            result = subprocess.run(
                [sys.executable, str(driver)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "exported")


if __name__ == "__main__":
    unittest.main()
