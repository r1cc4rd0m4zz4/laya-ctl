#!/usr/bin/env python3
"""Unit tests for laya-ctl controller logic, pre-flight checks, and memory profiles."""

import os
import sys
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

    def test_env_config_full_propagation(self):
        mock_env_config = {
            "LAYA_DEVICE": "mps",
            "CUSTOM_TELEMETRY": "enabled",
        }
        with patch.dict(laya_ctl.ENV_CONFIG, mock_env_config, clear=True):
            resolved = laya_ctl.get_resolved_env()
            self.assertEqual(resolved.get("LAYA_DEVICE"), "mps")
            self.assertEqual(resolved.get("CUSTOM_TELEMETRY"), "enabled")

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


if __name__ == "__main__":
    unittest.main()
