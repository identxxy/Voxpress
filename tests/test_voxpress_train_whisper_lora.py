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

    def test_summarize_loss_metrics_uses_average_loss(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_train_whisper_lora_metrics_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        summary = module.summarize_loss_metrics(
            [
                {"loss_avg": 2.0, "samples_seen": 8},
                {"loss_avg": 1.0, "samples_seen": 16},
            ]
        )

        self.assertEqual(summary["steps"], 2)
        self.assertEqual(summary["initial_loss_avg"], 2.0)
        self.assertEqual(summary["final_loss_avg"], 1.0)
        self.assertEqual(summary["mean_loss_avg"], 1.5)
        self.assertEqual(summary["samples_seen"], 16)

    def test_lora_targets_and_language_mode_defaults(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_train_whisper_lora_config_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(
            module.parse_lora_target_modules("q_proj, k_proj,v_proj,out_proj"),
            ["q_proj", "k_proj", "v_proj", "out_proj"],
        )
        self.assertEqual(
            module.parse_lora_target_modules(""),
            ["q_proj", "k_proj", "v_proj", "out_proj"],
        )
        self.assertEqual(module.tokenizer_language_for_text("hello world", "zh_en"), "en")
        self.assertEqual(module.tokenizer_language_for_text("你好 world", "zh_en"), "zh")
        self.assertEqual(module.processor_default_language("zh_en"), "zh")


if __name__ == "__main__":
    unittest.main()
