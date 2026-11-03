"""Failure-path tests for frontend-only deployment, without SSH or Docker access."""

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "frontend_update", Path(__file__).resolve().parents[1] / "deploy/production/update_frontend.py"
)
assert spec and spec.loader
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class FrontendDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "release").mkdir()
        (self.root / "run").mkdir()
        (self.root / "incoming").mkdir()
        self.env = "OTHER=unchanged\nATTACKSCOPE_FRONTEND_IMAGE=frontend:old\n"
        (self.root / "release/.env").write_text(self.env)
        self.directory = self.root / "transaction"
        self.directory.mkdir()
        (self.directory / "previous.env").write_text(self.env)
        self.state = {
            "phase": "staged",
            "image": "frontend:new",
            "image_id": "new-id",
            "previous_image_id": "old-id",
            "protected": {"backend": "same-id"},
            "candidate": "candidate-test",
        }
        self.active = "old-id"
        self.compose_calls = []
        self.addCleanup(patch.stopall)
        patch.object(update, "ROOT", self.root).start()
        patch.object(update, "protected", return_value=self.state["protected"]).start()
        patch.object(update, "healthy").start()
        patch.object(update, "ready").start()
        patch.object(update, "clean_candidate").start()
        patch.object(update, "inspect", side_effect=lambda _: {"Image": self.active}).start()
        patch.object(update, "compose", side_effect=self.compose).start()

    def compose(self, *args, **kwargs):
        self.compose_calls.append(args)
        content = (self.root / "release/.env").read_text()
        self.active = "new-id" if "frontend:new" in content else "old-id"
        return ""

    def test_failed_promotion_restores_previous_env_and_image(self):
        with patch.object(update, "ready", side_effect=RuntimeError("unhealthy")):
            with self.assertRaisesRegex(RuntimeError, "unhealthy"):
                update.promote(self.directory, self.state)
        self.assertEqual(self.state["phase"], "promoting")
        self.assertEqual(self.active, "new-id")
        update.abort(self.directory, self.state)
        self.assertEqual(self.active, "old-id")
        self.assertEqual((self.root / "release/.env").read_text(), self.env)
        self.assertEqual(self.state["phase"], "rolled_back")
        for call in self.compose_calls:
            self.assertEqual(call[-1], "frontend")
            self.assertIn("--no-deps", call)
            self.assertIn("--no-build", call)

    def test_abort_before_promotion_does_not_restart_live_services(self):
        update.abort(self.directory, self.state)
        self.assertEqual(self.compose_calls, [])
        self.assertEqual(self.active, "old-id")
        self.assertEqual(self.state["phase"], "aborted")

    def test_changed_protected_container_blocks_promotion(self):
        with patch.object(update, "protected", return_value={"backend": "other-id"}):
            with self.assertRaisesRegex(RuntimeError, "Protected components changed"):
                update.promote(self.directory, self.state)
        self.assertEqual(self.compose_calls, [])
        self.assertEqual((self.root / "release/.env").read_text(), self.env)

    def test_checksum_mismatch_never_loads_image_or_changes_env(self):
        archive = self.root / "incoming/rejected.tar"
        archive.write_bytes(b"corrupt-image")
        args = argparse.Namespace(
            release="rejected", commit="a" * 40, image_id="sha256:" + "b" * 64, checksum="0" * 64
        )
        with patch.object(update, "run") as docker:
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                update.stage(args, self.root / "rejected")
            docker.assert_not_called()
        self.assertEqual((self.root / "release/.env").read_text(), self.env)

    def test_ambiguous_image_configuration_is_rejected(self):
        for content in ("OTHER=only\n", self.env + self.env):
            with self.assertRaises(RuntimeError):
                update.replace_image(content, "frontend:new")

    def terminal_recovery(self, owner):
        release = "a" * 12 + "-20261103000000-abcd"
        directory = self.root / "updates" / release
        directory.mkdir(parents=True)
        (directory / "state.json").write_text(json.dumps({"phase": "complete"}))
        lock = self.root / "deploy.lock"
        lock.mkdir()
        (lock / "owner").write_text(owner or release)
        with patch.object(sys, "argv", ["helper", "abort", release]):
            with patch.object(update.os, "geteuid", return_value=0):
                update.main()
        self.assertEqual(self.compose_calls, [])
        return lock

    def test_terminal_checkpoint_releases_own_stale_lock(self):
        self.assertFalse(self.terminal_recovery(None).exists())

    def test_terminal_checkpoint_preserves_newer_transaction_lock(self):
        lock = self.terminal_recovery("newer-transaction")
        self.assertEqual((lock / "owner").read_text(), "newer-transaction")


if __name__ == "__main__":
    unittest.main()
