"""Tests for config safety: ensure dry_run is enforced and secrets are handled safely."""
import unittest
import os
import json
import tempfile

from modules.config import CFG, DEFAULTS, SHARED, load_config, SECRET_FIELDS


class TestDryRunDefault(unittest.TestCase):
    """Verify that dry_run is True by default and config files can't override it."""

    def test_defaults_are_dry_run(self):
        self.assertTrue(DEFAULTS["dry_run"])

    def test_defaults_environment_is_demo(self):
        self.assertEqual(DEFAULTS["environment"], "demo")

    def test_defaults_quickflip_disabled(self):
        self.assertFalse(DEFAULTS["quickflip_enabled"])

    def test_defaults_cross_arb_disabled(self):
        self.assertFalse(DEFAULTS["cross_arb_enabled"])

    def test_defaults_compounding_disabled(self):
        self.assertFalse(DEFAULTS["compounding_enabled"])


class TestConfigFileIgnoresDryRun(unittest.TestCase):
    """Config files with dry_run=false should NOT enable live trading."""

    def test_config_file_dry_run_false_ignored(self):
        """A config file setting dry_run=false must not enable live trading."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "kalshi_api_key_id": "test-key",
                "anthropic_api_key": "test-anthropic-key",
                "dry_run": False,
            }, f)
            config_path = f.name

        try:
            load_config(config_path=config_path, live_mode=False)
            self.assertTrue(CFG["dry_run"], "dry_run should be True even when config file says False")
        finally:
            os.unlink(config_path)

    def test_live_mode_flag_enables_live(self):
        """Only --live flag should enable live trading."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "kalshi_api_key_id": "test-key",
                "anthropic_api_key": "test-anthropic-key",
            }, f)
            config_path = f.name

        try:
            load_config(config_path=config_path, live_mode=True)
            self.assertFalse(CFG["dry_run"], "dry_run should be False when --live is passed")
        finally:
            os.unlink(config_path)
            # Reset to safe state
            CFG["dry_run"] = True
            SHARED["dry_run"] = True


class TestSecretFields(unittest.TestCase):
    """Verify that secret field list covers all sensitive config keys."""

    def test_api_keys_are_secret(self):
        self.assertIn("kalshi_api_key_id", SECRET_FIELDS)
        self.assertIn("anthropic_api_key", SECRET_FIELDS)

    def test_private_keys_are_secret(self):
        self.assertIn("polymarket_private_key", SECRET_FIELDS)
        self.assertIn("kalshi_private_key_path", SECRET_FIELDS)

    def test_passwords_are_secret(self):
        self.assertIn("email_password", SECRET_FIELDS)

    def test_example_config_has_no_real_secrets(self):
        """Verify the example config doesn't contain real credential values."""
        example_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                     "kalshi-config.example.json")
        if not os.path.exists(example_path):
            self.skipTest("Example config not found")

        with open(example_path) as f:
            example = json.load(f)

        for key in SECRET_FIELDS:
            value = example.get(key, "")
            if isinstance(value, str) and value:
                # Should be empty or a placeholder
                self.assertTrue(
                    value == "" or value.startswith("your-") or value.startswith("0x...") or value.startswith("sk-ant-..."),
                    f"Secret field '{key}' has suspicious value in example config: {value[:20]}..."
                )


class TestSharedStateSafety(unittest.TestCase):
    def test_shared_state_starts_dry_run(self):
        self.assertTrue(SHARED["dry_run"])


if __name__ == "__main__":
    unittest.main()
