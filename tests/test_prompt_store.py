import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from app.services.prompt_store import PromptStore


class PromptStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path("tests") / ".tmp_prompt_store"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.store_path = self.temp_root / f"{self._testMethodName}_{uuid4().hex}.json"

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_default_prompt_is_used_until_a_prompt_is_saved(self):
        store = PromptStore(
            storage_path=self.store_path,
            default_prompt="default prompt",
            default_opening_message="default opening",
        )

        snapshot = store.get_snapshot()

        self.assertIsNone(snapshot.active_version_id)
        self.assertEqual(snapshot.active_prompt, "default prompt")
        self.assertEqual(snapshot.active_opening_message, "default opening")
        self.assertEqual(snapshot.versions, [])

    def test_save_restore_and_reset_are_visible_in_history(self):
        store = PromptStore(
            storage_path=self.store_path,
            default_prompt="default prompt",
            default_opening_message="default opening",
        )

        first = store.save_prompt("first prompt", opening_message="first opening", updated_by="alice")
        second = store.save_prompt("second prompt", opening_message="second opening", updated_by="bob")
        restored = store.restore_version(first.id, updated_by="alice")
        reset = store.reset_to_default(updated_by="admin")

        snapshot = store.get_snapshot()

        self.assertEqual(snapshot.active_version_id, reset.id)
        self.assertEqual(snapshot.active_prompt, "default prompt")
        self.assertEqual(snapshot.active_opening_message, "default opening")
        self.assertEqual(
            [version.action for version in snapshot.versions],
            ["reset_to_default", "restore", "save", "save"],
        )
        self.assertEqual(snapshot.versions[1].source_version_id, first.id)
        self.assertEqual(restored.prompt, "first prompt")
        self.assertEqual(restored.opening_message, "first opening")
        self.assertEqual(second.prompt, "second prompt")


if __name__ == "__main__":
    unittest.main()
