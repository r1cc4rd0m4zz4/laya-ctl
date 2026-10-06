#!/usr/bin/env python3
"""Unit tests for laya-ctl controller logic."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import laya_ctl


class TestLayaCtl(unittest.TestCase):
    def test_environment_defaults(self):
        self.assertEqual(laya_ctl.HOST, "127.0.0.1")
        self.assertEqual(laya_ctl.PORT, 5292)
        self.assertEqual(laya_ctl.BASE_URL, "http://127.0.0.1:5292")

    def test_health_check_type(self):
        # Health check should return dict or None
        health = laya_ctl.check_health(timeout=0.5)
        self.assertTrue(health is None or isinstance(health, dict))
        if health:
            self.assertEqual(health.get("status"), "ok")


if __name__ == "__main__":
    unittest.main()
