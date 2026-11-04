#!/usr/bin/env python3
"""Unit tests for laya-ctl controller logic, pre-flight checks, and memory profiles."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import laya_ctl


class TestLayaCtl(unittest.TestCase):
    def test_environment_defaults(self):
        self.assertEqual(laya_ctl.HOST, "127.0.0.1")
        self.assertEqual(laya_ctl.PORT, 5292)
        self.assertEqual(laya_ctl.BASE_URL, "http://127.0.0.1:5292")

    def test_profiles_configuration(self):
        self.assertIn("balanced", laya_ctl.PROFILES)
        self.assertIn("performance", laya_ctl.PROFILES)
        self.assertIn("eco", laya_ctl.PROFILES)

        # Balanced: max 2 models, idle unload 300s
        bal = laya_ctl.PROFILES["balanced"]
        self.assertEqual(bal["LAYA_MAX_LOADED"], "2")
        self.assertEqual(bal["LAYA_IDLE_UNLOAD_SECONDS"], "300")

        # Performance: all 3 models in RAM, no unload
        perf = laya_ctl.PROFILES["performance"]
        self.assertEqual(perf["LAYA_MAX_LOADED"], "3")
        self.assertEqual(perf["LAYA_IDLE_UNLOAD_SECONDS"], "0")

        # Eco: 1 model in RAM
        eco = laya_ctl.PROFILES["eco"]
        self.assertEqual(eco["LAYA_MAX_LOADED"], "1")

    def test_health_check_type(self):
        health = laya_ctl.check_health(timeout=0.5)
        self.assertTrue(health is None or isinstance(health, dict))
        if health:
            self.assertEqual(health.get("status"), "ok")

    def test_version_parsing(self):
        self.assertEqual(laya_ctl.parse_version_tuple("0.4.21"), (0, 4, 21))
        self.assertEqual(laya_ctl.parse_version_tuple("0.4.20.post1"), (0, 4, 20))
        self.assertEqual(laya_ctl.parse_version_tuple("0.4.20rc2"), (0, 4, 20))
        self.assertEqual(laya_ctl.parse_version_tuple("1.0.0+cu121"), (1, 0, 0))

        min_tuple = laya_ctl.parse_version_tuple(laya_ctl.MIN_LAYA_VERSION)
        self.assertGreaterEqual(laya_ctl.parse_version_tuple("0.4.21"), min_tuple)
        self.assertGreaterEqual(laya_ctl.parse_version_tuple("0.4.20"), min_tuple)
        self.assertLess(laya_ctl.parse_version_tuple("0.4.19"), min_tuple)
        self.assertLess(laya_ctl.parse_version_tuple("0.3.99"), min_tuple)

    def test_minimum_laya_version_constant(self):
        self.assertEqual(laya_ctl.MIN_LAYA_VERSION, "0.4.20")

    @staticmethod
    def _resolve(env_config: dict, shell_env: dict, **kwargs) -> dict:
        """get_resolved_env() with a hermetic .env, shell environment and cache directory."""
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(laya_ctl, "BASE_DIR", tmp), \
             patch.dict(laya_ctl.ENV_CONFIG, env_config, clear=True), \
             patch.dict(os.environ, shell_env, clear=True):
            return laya_ctl.get_resolved_env(**kwargs)

    def test_env_file_laya_keys_are_propagated(self):
        resolved = self._resolve({"LAYA_DEVICE": "mps", "LAYA_MAX_LOADED": "1"}, {})
        self.assertEqual(resolved.get("LAYA_DEVICE"), "mps")
        self.assertEqual(resolved.get("LAYA_MAX_LOADED"), "1")

    def test_laya_device_auto_is_unset_for_torch(self):
        # 'auto' or empty string in LAYA_DEVICE crashes laya-serve (torch.device('auto') ValueError);
        # get_resolved_env() must unset it so laya-serve runs its native auto-detection.
        resolved = self._resolve({"LAYA_DEVICE": "auto"}, {})
        self.assertNotIn("LAYA_DEVICE", resolved)

        resolved_empty = self._resolve({"LAYA_DEVICE": "  "}, {})
        self.assertNotIn("LAYA_DEVICE", resolved_empty)

        resolved_explicit = self._resolve({"LAYA_DEVICE": "cuda:0"}, {})
        self.assertEqual(resolved_explicit.get("LAYA_DEVICE"), "cuda:0")

    def test_env_file_non_laya_keys_are_never_propagated(self):
        # A .env in the working directory must not be able to inject loader or interpreter variables.
        hostile = {
            "PATH": "/tmp/evil",
            "PYTHONPATH": "/tmp/evil",
            "LD_PRELOAD": "/tmp/evil.so",
            "DYLD_INSERT_LIBRARIES": "/tmp/evil.dylib",
            "CUSTOM_TELEMETRY": "enabled",
        }
        resolved = self._resolve(hostile, {"PATH": "/usr/bin"})
        for key in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "CUSTOM_TELEMETRY"):
            self.assertNotIn(key, resolved)
        self.assertEqual(resolved["PATH"], "/usr/bin")
        self.assertNotIn("/tmp/evil", resolved["PYTHONPATH"])

    def test_shell_environment_wins_over_env_file(self):
        resolved = self._resolve(
            {"LAYA_DEVICE": "cpu", "LAYA_JEV_STRICT": "1", "LAYA_MAX_LOADED": "1"},
            {"LAYA_DEVICE": "mps", "LAYA_JEV_STRICT": "0", "LAYA_MAX_LOADED": "3"},
        )
        self.assertEqual(resolved["LAYA_DEVICE"], "mps")
        self.assertEqual(resolved["LAYA_MAX_LOADED"], "3")
        self.assertEqual(resolved["LAYA_JEV_STRICT"], "0")

    def test_strict_flag_wins_over_shell_environment(self):
        resolved = self._resolve({}, {"LAYA_JEV_STRICT": "0"}, strict=True)
        self.assertEqual(resolved["LAYA_JEV_STRICT"], "1")

    def test_is_enabled_matches_laya_serve_spellings(self):
        for value in ("1", "true", "TRUE", " yes ", "on"):
            self.assertTrue(laya_ctl.is_enabled(value), value)
        for value in (None, "", "  ", "0", "false", "no", "off", "2", "enabled"):
            self.assertFalse(laya_ctl.is_enabled(value), repr(value))

    def test_strict_spelling_true_in_env_file_is_normalised(self):
        resolved = self._resolve({"LAYA_JEV_STRICT": "true"}, {})
        self.assertEqual(resolved["LAYA_JEV_STRICT"], "1")

    def test_unknown_profile_falls_back_and_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, LAYA_PROFILE="fast", HOME=tmp)
            res = subprocess.run(
                [sys.executable, "-c", "import laya_ctl; print(laya_ctl.ACTIVE_PROFILE)"],
                env=env, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                capture_output=True, text=True, timeout=30, check=False,
            )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), "balanced")
        self.assertIn("unknown LAYA_PROFILE 'fast'", res.stderr)

    def test_strict_mode_propagation(self):
        # 1. Via CLI / explicit flag
        resolved_strict = laya_ctl.get_resolved_env(strict=True)
        self.assertEqual(resolved_strict.get("LAYA_JEV_STRICT"), "1")

        # 2. Via ENV_CONFIG / .env
        with patch.dict(laya_ctl.ENV_CONFIG, {"LAYA_JEV_STRICT": "1"}, clear=True):
            resolved_from_env = laya_ctl.get_resolved_env(strict=False)
            self.assertEqual(resolved_from_env.get("LAYA_JEV_STRICT"), "1")

    def test_probe_laya_compatibility_missing_binary(self):
        with patch("shutil.which", return_value=None):
            compatible, ver, msg = laya_ctl.probe_laya_compatibility()
            self.assertFalse(compatible)
            self.assertIsNone(ver)
            self.assertIn("not found in PATH", msg)

    def test_probe_laya_compatibility_outdated(self):
        with patch("shutil.which", return_value="/mock/bin/laya-serve"), \
             patch("laya_ctl.get_installed_laya_version", return_value="0.3.5"):
            compatible, ver, msg = laya_ctl.probe_laya_compatibility()
            self.assertFalse(compatible)
            self.assertEqual(ver, "0.3.5")
            self.assertIn("below minimum recommended", msg)

    def test_probe_laya_compatibility_valid(self):
        with patch("shutil.which", return_value="/mock/bin/laya-serve"), \
             patch("laya_ctl.get_installed_laya_version", return_value="0.4.21"):
            compatible, ver, msg = laya_ctl.probe_laya_compatibility()
            self.assertTrue(compatible)
            self.assertEqual(ver, "0.4.21")
            self.assertIn("fully compatible", msg)


class TestIdleUnloadKeepsProcessAlive(unittest.TestCase):
    """Regression: an idle unload must never terminate laya-serve (the TCP port must stay open)."""

    def _run_with_hook(self, fake_laya: bool) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(laya_ctl, "BASE_DIR", tmp):
                lib_dir = laya_ctl.ensure_reclaimer_hook()
            pythonpath = [lib_dir]
            if fake_laya:
                pkg = os.path.join(tmp, "fakepkg", "laya")
                os.makedirs(pkg)
                with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as f:
                    f.write("")
                with open(os.path.join(pkg, "router.py"), "w", encoding="utf-8") as f:
                    f.write(
                        "class Router:\n"
                        "    def _evict_locked(self):\n"
                        "        return 'evicted'\n"
                        "    def unload(self, name=None):\n"
                        "        return 'unloaded'\n"
                    )
                pythonpath.append(os.path.join(tmp, "fakepkg"))
            script = (
                "from laya import router\n"
                "r = router.Router()\n"
                "print(type(r).unload.__name__)\n"
                "print(r.unload())\n"
                "print(r._evict_locked())\n"
                "print('ALIVE')\n"
            ) if fake_laya else "print('ALIVE')\n"
            env = dict(os.environ, PYTHONPATH=os.pathsep.join(pythonpath), HOME=tmp)
            return subprocess.run(
                [sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30, check=False
            )

    def test_hook_source_never_exits_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(laya_ctl, "BASE_DIR", tmp):
                lib_dir = laya_ctl.ensure_reclaimer_hook()
            with open(os.path.join(lib_dir, "sitecustomize.py"), encoding="utf-8") as f:
                source = f.read()
        self.assertNotIn("_exit", source)
        self.assertNotIn("AUTO_HIBERNATE", source)
        self.assertNotIn("hibernat", source.lower())

    def test_unload_and_evict_are_patched_and_process_survives(self):
        res = self._run_with_hook(fake_laya=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.split()
        self.assertEqual(lines, ["patched_unload", "unloaded", "evicted", "ALIVE"])
        self.assertNotIn("could not patch", res.stderr)

    def test_missing_router_is_reported_not_silenced(self):
        res = subprocess.run(
            [sys.executable, "-c", "print('ALIVE')"],
            env=dict(os.environ, PYTHONPATH=self._hook_dir_without_laya()),
            capture_output=True, text=True, timeout=30, check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("ALIVE", res.stdout)
        self.assertIn("could not patch router", res.stderr)

    def _hook_dir_without_laya(self) -> str:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        with patch.object(laya_ctl, "BASE_DIR", self._tmp.name):
            return laya_ctl.ensure_reclaimer_hook()


class TestStatusReporting(unittest.TestCase):
    def _status(self, health: dict) -> str:
        buf = io.StringIO()
        with patch.object(laya_ctl, "check_health", return_value=health), \
             patch.object(laya_ctl, "get_running_pid", return_value=None), \
             patch.object(laya_ctl, "get_installed_laya_version", return_value="0.4.22"), \
             contextlib.redirect_stdout(buf):
            laya_ctl.service_status()
        return buf.getvalue()

    def test_idle_server_is_reported_as_idle_not_hibernated(self):
        out = self._status({"status": "ok", "loaded": [], "device": "mps"})
        self.assertIn("none (idle: models reload on next request)", out)
        self.assertNotIn("HIBERNATED", out.upper())

    def test_resident_models_are_listed(self):
        out = self._status({"status": "ok", "loaded": ["english", "multilingual"], "device": "mps"})
        self.assertIn("english, multilingual", out)

    def test_liveness_only_health_is_not_reported_as_idle(self):
        out = self._status({"status": "ok"})
        self.assertIn("hidden (liveness only", out)
        self.assertNotIn("idle", out)


if __name__ == "__main__":
    unittest.main()
