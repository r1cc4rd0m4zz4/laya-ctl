#!/usr/bin/env python3
"""Unit tests for laya-ctl controller logic and memory profiles."""

import os
import sys
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
