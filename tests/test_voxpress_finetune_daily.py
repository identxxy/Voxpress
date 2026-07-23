import importlib.machinery
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "voxpress-finetune-daily"


class VoxpressFinetuneDailyTest(unittest.TestCase):
    def write_sample_db(self, root):
        root.mkdir(parents=True)
        audio_dir = root / "audio" / "2026-05-29"
        audio_dir.mkdir(parents=True)
        audio = audio_dir / "sample.wav"
        audio.write_bytes(b"RIFF" + b"0" * 128)
        conn = sqlite3.connect(root / "index.sqlite")
        conn.execute(
            """
            create table samples (
                id text primary key,
                created_at text not null,
                audio_path text not null,
                audio_format text not null,
                duration_seconds real,
                audio_bytes integer not null,
                raw_text text not null,
                preview_text text not null,
                corrected_text text not null,
                model text,
                language_mode text,
                source text not null
            )
            """
        )
        conn.execute(
            """
            insert into samples values (
                'sample', '2026-05-29T02:15:30+08:00',
                'audio/2026-05-29/sample.wav', 'wav_pcm_s16le_16000_mono',
                1.0, 132, 'raw', 'preview', 'corrected', 'large-v3-turbo',
                'zh_en', 'voxpress-preview'
            )
            """
        )
        conn.commit()
        conn.close()

    def test_run_trains_promotes_fixed_current_model_and_prunes_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            correction_dir = base / "corrections"
            self.write_sample_db(correction_dir)
            train_script = base / "fake_train.py"
            train_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import pathlib
                    import sys

                    output_dir = pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1])
                    output_dir.mkdir(parents=True, exist_ok=True)
                    model = output_dir / 'deploy' / 'ggml-model.bin'
                    model.parent.mkdir(parents=True, exist_ok=True)
                    model.write_bytes(b'model')
                    (output_dir / 'deploy' / 'merged-hf').mkdir(parents=True, exist_ok=True)
                    (output_dir / 'deploy' / 'merged-hf' / 'pytorch_model.bin').write_bytes(b'base')
                    (output_dir / 'train-result.json').write_text(
                        json.dumps({'deploy_model_path': str(model)}),
                        encoding='utf-8',
                    )
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            nvidia_smi = base / "nvidia-smi"
            nvidia_smi.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "args = ' '.join(sys.argv[1:])\n"
                "if '--query-gpu' in args:\n"
                "    print('0')\n"
                "elif '--query-compute-apps' in args:\n"
                "    print('')\n"
                "elif 'pmon' in args:\n"
                "    print('# gpu pid type sm mem enc dec command')\n"
                "else:\n"
                "    print('')\n",
                encoding="utf-8",
            )
            systemctl = base / "systemctl"
            systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            nvidia_smi.chmod(0o755)
            systemctl.chmod(0o755)
            config = base / "config.toml"
            config.write_text(
                '[whisper]\nmodel = "large-v3-turbo"\nmode="cli"\nwhisper_cli_path="/tmp/old-cli"\ninitial_prompt="Spatial terms"\n',
                encoding="utf-8",
            )
            settings = base / "settings.json"
            settings.write_text(
                json.dumps({"recognition_model_mode": "personal"}),
                encoding="utf-8",
            )
            prompt_backup = base / "base-initial-prompt.txt"
            old_run = base / "runs" / "20260528T010203"
            old_run.mkdir(parents=True)
            (old_run / "stale.bin").write_bytes(b"stale")

            env = os.environ.copy()
            env.update(
                {
                    "VOXPRESS_CORRECTION_DIR": str(correction_dir),
                    "VOXPRESS_NVIDIA_SMI": str(nvidia_smi),
                    "VOXPRESS_SYSTEMCTL": str(systemctl),
                    "VOXTYPE_CONFIG_PATH": str(config),
                    "VOXPRESS_INITIAL_PROMPT_BACKUP": str(prompt_backup),
                    "VOXPRESS_SETTINGS": str(settings),
                    "VOXPRESS_TRAIN_COMMAND": f"{sys.executable} {train_script} --manifest {{manifest}} --output-dir {{output_dir}} --max-minutes {{max_minutes}}",
                    "VOXPRESS_GPU_CHECK_INTERVAL_SECONDS": "0",
                    "VOXPRESS_MODEL_RUNS_DIR": str(base / "runs"),
                    "VOXPRESS_SKIP_MODEL_SMOKE_TEST": "1",
                    "VOXPRESS_AUTO_PROMOTE_MODEL": "1",
                }
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "run", "--force-time"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "promoted", payload)
            current_model = base / "current" / "voxpress-personal-whisper.bin"
            self.assertEqual(payload["model_path"], str(current_model))
            self.assertEqual(current_model.read_bytes(), b"model")
            metadata = json.loads((base / "current" / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["model_path"], str(current_model))
            self.assertEqual(metadata["source_run_dir"], payload["run_dir"])
            config_text = config.read_text(encoding="utf-8")
            self.assertIn(str(current_model), config_text)
            self.assertFalse(
                any(line.strip().split("=", 1)[0].strip() == "mode" for line in config_text.splitlines())
            )
            self.assertNotIn("whisper_cli_path", config_text)
            self.assertNotIn("initial_prompt", config_text)
            self.assertEqual(prompt_backup.read_text(encoding="utf-8"), "Spatial terms\n")
            self.assertFalse(old_run.exists())
            run_dir = Path(payload["run_dir"])
            self.assertTrue((run_dir / "train-result.json").is_file())
            train_result = json.loads((run_dir / "train-result.json").read_text(encoding="utf-8"))
            self.assertEqual(train_result["deploy_model_path"], str(current_model))
            self.assertEqual(train_result["source_deploy_model_path"], str(run_dir / "deploy" / "ggml-model.bin"))
            self.assertFalse((run_dir / "deploy").exists())

    def test_base_recognition_mode_keeps_live_config_on_base_after_promotion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            correction_dir = base / "corrections"
            self.write_sample_db(correction_dir)
            train_script = base / "fake_train.py"
            train_script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import pathlib
                    import sys

                    output_dir = pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1])
                    output_dir.mkdir(parents=True, exist_ok=True)
                    model = output_dir / 'deploy' / 'ggml-model.bin'
                    model.parent.mkdir(parents=True, exist_ok=True)
                    model.write_bytes(b'model')
                    (output_dir / 'train-result.json').write_text(
                        json.dumps({'deploy_model_path': str(model)}),
                        encoding='utf-8',
                    )
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            nvidia_smi = base / "nvidia-smi"
            nvidia_smi.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "args = ' '.join(sys.argv[1:])\n"
                "if '--query-gpu' in args:\n"
                "    print('0')\n"
                "elif '--query-compute-apps' in args:\n"
                "    print('')\n"
                "elif 'pmon' in args:\n"
                "    print('# gpu pid type sm mem enc dec command')\n"
                "else:\n"
                "    print('')\n",
                encoding="utf-8",
            )
            systemctl_log = base / "systemctl.log"
            systemctl = base / "systemctl"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                f"echo \"$*\" >> {str(systemctl_log)!r}\n"
                "exit 0\n",
                encoding="utf-8",
            )
            nvidia_smi.chmod(0o755)
            systemctl.chmod(0o755)
            config = base / "config.toml"
            config.write_text("[whisper]\nmodel = \"large-v3-turbo\"\n", encoding="utf-8")
            settings = base / "settings.json"
            settings.write_text(
                json.dumps({"recognition_model_mode": "base"}),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env.update(
                {
                    "VOXPRESS_CORRECTION_DIR": str(correction_dir),
                    "VOXPRESS_NVIDIA_SMI": str(nvidia_smi),
                    "VOXPRESS_SYSTEMCTL": str(systemctl),
                    "VOXTYPE_CONFIG_PATH": str(config),
                    "VOXPRESS_SETTINGS": str(settings),
                    "VOXPRESS_TRAIN_COMMAND": f"{sys.executable} {train_script} --manifest {{manifest}} --output-dir {{output_dir}} --max-minutes {{max_minutes}}",
                    "VOXPRESS_GPU_CHECK_INTERVAL_SECONDS": "0",
                    "VOXPRESS_MODEL_RUNS_DIR": str(base / "runs"),
                    "VOXPRESS_SKIP_MODEL_SMOKE_TEST": "1",
                    "VOXPRESS_AUTO_PROMOTE_MODEL": "1",
                }
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "run", "--force-time"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "promoted", payload)
            current_model = base / "current" / "voxpress-personal-whisper.bin"
            self.assertEqual(payload["model_path"], str(current_model))
            self.assertEqual(current_model.read_bytes(), b"model")
            self.assertEqual(
                config.read_text(encoding="utf-8"),
                '[whisper]\nmodel = "large-v3-turbo"\n',
            )
            self.assertFalse(systemctl_log.exists())

    def test_wrapper_marker_is_not_promotable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            correction_dir = base / "corrections"
            self.write_sample_db(correction_dir)
            deploy_model = base / "wrapper-marker.bin"
            train_script = base / "fake_train.py"
            train_script.write_text(
                textwrap.dedent(
                    f"""
                    import json
                    import pathlib
                    import sys

                    output_dir = pathlib.Path(sys.argv[sys.argv.index('--output-dir') + 1])
                    output_dir.mkdir(parents=True, exist_ok=True)
                    model = pathlib.Path({str(deploy_model)!r})
                    model.write_text(json.dumps({{'deploy_type': 'voxpress-whisper-cli-wrapper'}}), encoding='utf-8')
                    (output_dir / 'train-result.json').write_text(
                        json.dumps({{'deploy_model_path': str(model)}}),
                        encoding='utf-8',
                    )
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            nvidia_smi = base / "nvidia-smi"
            nvidia_smi.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "args = ' '.join(sys.argv[1:])\n"
                "if '--query-gpu' in args:\n"
                "    print('0')\n"
                "elif '--query-compute-apps' in args:\n"
                "    print('')\n"
                "elif 'pmon' in args:\n"
                "    print('# gpu pid type sm mem enc dec command')\n"
                "else:\n"
                "    print('')\n",
                encoding="utf-8",
            )
            systemctl = base / "systemctl"
            systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            nvidia_smi.chmod(0o755)
            systemctl.chmod(0o755)
            config = base / "config.toml"
            config.write_text("[whisper]\nmodel = \"large-v3-turbo\"\n", encoding="utf-8")

            env = os.environ.copy()
            env.update(
                {
                    "VOXPRESS_CORRECTION_DIR": str(correction_dir),
                    "VOXPRESS_NVIDIA_SMI": str(nvidia_smi),
                    "VOXPRESS_SYSTEMCTL": str(systemctl),
                    "VOXTYPE_CONFIG_PATH": str(config),
                    "VOXPRESS_TRAIN_COMMAND": f"{sys.executable} {train_script} --manifest {{manifest}} --output-dir {{output_dir}} --max-minutes {{max_minutes}}",
                    "VOXPRESS_GPU_CHECK_INTERVAL_SECONDS": "0",
                    "VOXPRESS_MODEL_RUNS_DIR": str(base / "runs"),
                    "VOXPRESS_SKIP_MODEL_SMOKE_TEST": "1",
                    "VOXPRESS_AUTO_PROMOTE_MODEL": "1",
                }
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "run", "--force-time"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "trained")
            self.assertEqual(payload["reason"], "deploy_model_not_promotable")
            self.assertEqual(config.read_text(encoding="utf-8"), '[whisper]\nmodel = "large-v3-turbo"\n')

    def test_default_trainer_missing_dependencies_skips_without_marking_day(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            correction_dir = base / "corrections"
            self.write_sample_db(correction_dir)
            script_dir = base / "bin"
            script_dir.mkdir()
            fake_daily = script_dir / "voxpress-finetune-daily"
            fake_trainer = script_dir / "voxpress-train-whisper-lora"
            fake_daily.write_text("", encoding="utf-8")
            fake_trainer.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "print('Missing training dependencies: torch', file=sys.stderr)\n"
                "raise SystemExit(2)\n",
                encoding="utf-8",
            )
            fake_trainer.chmod(0o755)

            loader = importlib.machinery.SourceFileLoader(
                "voxpress_finetune_daily_test", str(SCRIPT)
            )
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.__file__ = str(fake_daily)

            previous_env = os.environ.copy()
            os.environ.clear()
            os.environ.update(
                {
                    "VOXPRESS_CORRECTION_DIR": str(correction_dir),
                    "VOXPRESS_MODEL_RUNS_DIR": str(base / "runs"),
                }
            )
            try:
                result = module.run_daily(type("Args", (), {"force_time": True, "ignore_gpu": True})())
            finally:
                os.environ.clear()
                os.environ.update(previous_env)

            self.assertEqual(result["status"], "skipped")
            self.assertEqual(result["reason"], "training_dependencies_missing")
            self.assertFalse((correction_dir / "auto_train_state.json").exists())

    def test_gpu_busy_skips_training(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            correction_dir = base / "corrections"
            self.write_sample_db(correction_dir)
            nvidia_smi = base / "nvidia-smi"
            nvidia_smi.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "if '--query-gpu' in ' '.join(sys.argv[1:]): print('99')\n"
                "else: print('')\n",
                encoding="utf-8",
            )
            nvidia_smi.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "VOXPRESS_CORRECTION_DIR": str(correction_dir),
                    "VOXPRESS_NVIDIA_SMI": str(nvidia_smi),
                    "VOXPRESS_GPU_CHECK_INTERVAL_SECONDS": "0",
                }
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "run", "--force-time"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "skipped")
            self.assertEqual(payload["reason"], "gpu_busy")

    def test_degenerate_smoke_transcription_is_rejected(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_finetune_daily_degenerate_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(module.is_degenerate_transcription("!" * 80))
        self.assertTrue(
            module.is_degenerate_transcription(
                "experiencednocnocnocnocnocnocnocnocnoc PK PK PK PK PK PK PK PK PK PK "
                "kindkindkindkindkindkindkindkindkindkind"
            )
        )
        self.assertFalse(module.is_degenerate_transcription("OK,我同意,Geometry Loss"))

    def test_daily_train_watchdog_defaults_to_disabled(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_finetune_daily_watchdog_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        previous = os.environ.get("VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS")
        os.environ.pop("VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS", None)
        try:
            self.assertIsNone(module.train_watchdog_timeout({}, 30))
            os.environ["VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS"] = "120"
            self.assertEqual(module.train_watchdog_timeout({}, 30), 120)
            os.environ["VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS"] = "0"
            self.assertIsNone(module.train_watchdog_timeout({}, 30))
        finally:
            if previous is None:
                os.environ.pop("VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS", None)
            else:
                os.environ["VOXPRESS_DAILY_TRAIN_WATCHDOG_SECONDS"] = previous

    def test_default_train_command_passes_epoch_limit(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_finetune_daily_epoch_command_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        cmd = module.default_train_command("manifest.json", "out", 30, 5, {})
        self.assertIn("--max-minutes", cmd)
        self.assertIn("30", cmd)
        self.assertIn("--max-epochs", cmd)
        self.assertIn("5", cmd)
        self.assertIn("--language", cmd)
        self.assertIn("zh_en", cmd)

    def test_local_model_smoke_uses_temp_config_with_absolute_model_path(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_finetune_daily_smoke_prompt_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            audio = base / "sample.wav"
            audio.write_bytes(b"RIFF" + b"0" * 128)
            deploy_model = base / "ggml-personal.bin"
            deploy_model.write_bytes(b"ggml")
            config = base / "config.toml"
            config.write_text(
                '[whisper]\nmodel = "large-v3-turbo"\nmode = "remote"\nwhisper_cli_path = "/tmp/old-cli"\nlanguage = ["en", "zh"]\n',
                encoding="utf-8",
            )
            voxtype_args = base / "voxtype-args.json"
            voxtype = base / "voxtype.py"
            voxtype.write_text(
                textwrap.dedent(
                    f"""
                    #!/usr/bin/env python3
                    import json
                    import pathlib
                    import sys

                    config_path = pathlib.Path(sys.argv[sys.argv.index('--config') + 1])
                    config_text = config_path.read_text(encoding='utf-8')
                    pathlib.Path({str(voxtype_args)!r}).write_text(
                        json.dumps(sys.argv[1:]),
                        encoding='utf-8',
                    )
                    if {str(deploy_model)!r} in config_text:
                        print('corrected text')
                    else:
                        print('wrong output')
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            voxtype.chmod(0o755)

            previous_voxtype = os.environ.get("VOXPRESS_VOXTYPE_BIN")
            previous_config = os.environ.get("VOXTYPE_CONFIG_PATH")
            os.environ["VOXPRESS_VOXTYPE_BIN"] = str(voxtype)
            os.environ["VOXTYPE_CONFIG_PATH"] = str(config)
            try:
                smoke_dir = base / "smoke-output"
                ok, reason = module.model_smoke_test(
                    deploy_model,
                    [{"audio_path": str(audio), "text": "corrected text"}],
                    smoke_dir,
                    settings={"model_gate_sample_count": 1},
                )
            finally:
                if previous_voxtype is None:
                    os.environ.pop("VOXPRESS_VOXTYPE_BIN", None)
                else:
                    os.environ["VOXPRESS_VOXTYPE_BIN"] = previous_voxtype
                if previous_config is None:
                    os.environ.pop("VOXTYPE_CONFIG_PATH", None)
                else:
                    os.environ["VOXTYPE_CONFIG_PATH"] = previous_config

            self.assertTrue(ok, reason)
            args = json.loads(voxtype_args.read_text(encoding="utf-8"))
            self.assertIn("--config", args)
            self.assertIn("--whisper-mode", args)
            self.assertIn("local", args)
            self.assertNotIn("--model", args)
            smoke_config = smoke_dir / "candidate-smoke.config.toml"
            self.assertIn(str(deploy_model), smoke_config.read_text(encoding="utf-8"))
            self.assertIn('mode = "local"', smoke_config.read_text(encoding="utf-8"))
            self.assertNotIn("whisper_cli_path", smoke_config.read_text(encoding="utf-8"))
            self.assertNotIn("initial_prompt", smoke_config.read_text(encoding="utf-8"))
            quality = json.loads((smoke_dir / "model-quality-gate.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["status"], "passed")
            self.assertLess(quality["candidate_error_avg"], quality["base_error_avg"])

    def test_quality_gate_rejects_candidate_that_is_not_better_than_base(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_finetune_daily_quality_gate_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            audio = base / "sample.wav"
            audio.write_bytes(b"RIFF" + b"0" * 128)
            deploy_model = base / "ggml-personal.bin"
            deploy_model.write_bytes(b"ggml")
            config = base / "config.toml"
            config.write_text('[whisper]\nmodel = "large-v3-turbo"\n', encoding="utf-8")
            voxtype = base / "voxtype.py"
            voxtype.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env python3
                    print('wrong output')
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            voxtype.chmod(0o755)

            previous_voxtype = os.environ.get("VOXPRESS_VOXTYPE_BIN")
            previous_config = os.environ.get("VOXTYPE_CONFIG_PATH")
            os.environ["VOXPRESS_VOXTYPE_BIN"] = str(voxtype)
            os.environ["VOXTYPE_CONFIG_PATH"] = str(config)
            try:
                smoke_dir = base / "smoke-output"
                ok, reason = module.model_smoke_test(
                    deploy_model,
                    [{"audio_path": str(audio), "text": "corrected text"}],
                    smoke_dir,
                    settings={"model_gate_sample_count": 1},
                )
            finally:
                if previous_voxtype is None:
                    os.environ.pop("VOXPRESS_VOXTYPE_BIN", None)
                else:
                    os.environ["VOXPRESS_VOXTYPE_BIN"] = previous_voxtype
                if previous_config is None:
                    os.environ.pop("VOXTYPE_CONFIG_PATH", None)
                else:
                    os.environ["VOXTYPE_CONFIG_PATH"] = previous_config

            self.assertFalse(ok)
            self.assertEqual(reason, "quality_gate_not_better_than_base")
            quality = json.loads((smoke_dir / "model-quality-gate.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["status"], "failed")
            self.assertEqual(quality["reason"], "quality_gate_not_better_than_base")

    def test_empty_transcription_log_is_parsed_as_empty_output(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_finetune_daily_extract_transcription_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(
            module.extract_transcription('INFO Transcription completed in 0.30s: ""\n\n'),
            "",
        )
        self.assertEqual(
            module.extract_transcription('INFO Transcription completed in 0.30s: "用连续的3帧去跑"\n\n用连续的3帧去跑\n'),
            "用连续的3帧去跑",
        )

    def test_raw_training_history_is_synced_by_run_date(self):
        loader = importlib.machinery.SourceFileLoader(
            "voxpress_finetune_daily_history_sync_test", str(SCRIPT)
        )
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        previous = os.environ.get("VOXPRESS_TRAINING_HISTORY_DIR")
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            os.environ["VOXPRESS_TRAINING_HISTORY_DIR"] = str(base / "history")
            try:
                run_dir = base / "runs" / "20260608T010203"
                run_dir.mkdir(parents=True)
                (run_dir / "train-metrics.jsonl").write_text('{"step": 1}\n', encoding="utf-8")
                (run_dir / "train.stdout.log").write_text("step=1\n", encoding="utf-8")
                (run_dir / "model-quality-gate.json").write_text('{"status": "passed"}\n', encoding="utf-8")

                copied = module.sync_raw_training_history(run_dir)
                raw_dir = base / "history" / "runs" / "2026-06-08" / "20260608T010203"

                self.assertEqual(
                    copied,
                    ["train-metrics.jsonl", "train.stdout.log", "model-quality-gate.json"],
                )
                self.assertEqual((raw_dir / "train.stdout.log").read_text(encoding="utf-8"), "step=1\n")
                self.assertEqual(
                    (raw_dir / "model-quality-gate.json").read_text(encoding="utf-8"),
                    '{"status": "passed"}\n',
                )
            finally:
                if previous is None:
                    os.environ.pop("VOXPRESS_TRAINING_HISTORY_DIR", None)
                else:
                    os.environ["VOXPRESS_TRAINING_HISTORY_DIR"] = previous


if __name__ == "__main__":
    unittest.main()
