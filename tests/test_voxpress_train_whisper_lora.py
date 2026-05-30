import importlib.machinery
import importlib.util
import os
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-train-whisper-lora"


class VoxpressTrainWhisperLoraTest(unittest.TestCase):
    def test_export_timeout_defaults_to_disabled(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_train_whisper_lora_timeout_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        previous = os.environ.get("VOXPRESS_EXPORT_TIMEOUT_SECONDS")
        os.environ.pop("VOXPRESS_EXPORT_TIMEOUT_SECONDS", None)
        try:
            self.assertIsNone(module.export_timeout_seconds())
            os.environ["VOXPRESS_EXPORT_TIMEOUT_SECONDS"] = "300"
            self.assertEqual(module.export_timeout_seconds(), 300)
            os.environ["VOXPRESS_EXPORT_TIMEOUT_SECONDS"] = "0"
            self.assertIsNone(module.export_timeout_seconds())
        finally:
            if previous is None:
                os.environ.pop("VOXPRESS_EXPORT_TIMEOUT_SECONDS", None)
            else:
                os.environ["VOXPRESS_EXPORT_TIMEOUT_SECONDS"] = previous

    def test_sample_presentation_limit_uses_epochs(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_train_whisper_lora_epoch_limit_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.sample_presentation_limit(sample_count=2, max_epochs=5), 10)
        self.assertEqual(module.sample_presentation_limit(sample_count=100, max_epochs=5), 500)
        self.assertIsNone(module.sample_presentation_limit(sample_count=2, max_epochs=0))


if __name__ == "__main__":
    unittest.main()
