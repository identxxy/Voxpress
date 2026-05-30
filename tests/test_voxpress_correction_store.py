import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-correction-store"


class VoxpressCorrectionStoreTest(unittest.TestCase):
    def run_store(self, args, payload=None, env=None):
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            input=json.dumps(payload) if payload is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=merged_env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def payload(self, audio_path, text="corrected text", created_at="2026-05-29T02:15:30+08:00"):
        return {
            "audio_path": str(audio_path),
            "created_at": created_at,
            "duration_seconds": 1.0,
            "raw_text": "raw text",
            "preview_text": "preview text",
            "corrected_text": text,
            "model": "large-v3-turbo",
            "language_mode": "zh_en",
            "source": "voxpress-preview",
        }

    def write_audio(self, path, size=128):
        path.write_bytes(b"RIFF" + b"\0" * size)

    def test_save_edited_moves_audio_and_writes_sqlite_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "corrections"
            source = Path(tmpdir) / "clip.wav"
            self.write_audio(source)

            response = self.run_store(
                ["save-edited"],
                self.payload(source),
                {"VOXPRESS_CORRECTION_DIR": str(root)},
            )

            self.assertTrue(response["saved"])
            self.assertFalse(source.exists())
            saved_audio = root / response["audio_path"]
            self.assertTrue(saved_audio.exists())

            db = sqlite3.connect(root / "index.sqlite")
            row = db.execute(
                "select id, audio_path, raw_text, preview_text, corrected_text from samples"
            ).fetchone()
            db.close()
            self.assertEqual(row[0], response["id"])
            self.assertEqual(row[1], response["audio_path"])
            self.assertEqual(row[2], "raw text")
            self.assertEqual(row[3], "preview text")
            self.assertEqual(row[4], "corrected text")

    def test_retention_deletes_oldest_samples_when_sample_cap_exceeded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "corrections"
            env = {
                "VOXPRESS_CORRECTION_DIR": str(root),
                "VOXPRESS_CORRECTION_MAX_SAMPLES": "1",
            }
            first = Path(tmpdir) / "first.wav"
            second = Path(tmpdir) / "second.wav"
            self.write_audio(first)
            self.write_audio(second)

            first_response = self.run_store(
                ["save-edited"],
                self.payload(first, text="first", created_at="2026-05-29T02:15:30+08:00"),
                env,
            )
            second_response = self.run_store(
                ["save-edited"],
                self.payload(second, text="second", created_at="2026-05-29T02:16:30+08:00"),
                env,
            )

            self.assertFalse((root / first_response["audio_path"]).exists())
            self.assertTrue((root / second_response["audio_path"]).exists())
            db = sqlite3.connect(root / "index.sqlite")
            rows = db.execute("select corrected_text from samples order by created_at").fetchall()
            db.close()
            self.assertEqual(rows, [("second",)])

    def test_usage_and_purge_report_store_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "corrections"
            source = Path(tmpdir) / "clip.wav"
            self.write_audio(source, size=256)
            env = {"VOXPRESS_CORRECTION_DIR": str(root)}

            self.run_store(["save-edited"], self.payload(source), env)
            usage = self.run_store(["usage"], env=env)
            self.assertEqual(usage["sample_count"], 1)
            self.assertGreater(usage["audio_bytes"], 0)

            purged = self.run_store(["purge", "--yes"], env=env)
            self.assertEqual(purged["sample_count"], 0)
            self.assertEqual(purged["audio_bytes"], 0)
            self.assertEqual(self.run_store(["usage"], env=env)["sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
