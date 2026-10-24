import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import gupload_menu as menu
import gupload


class MenuBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config_root = self.root / "config"
        self.config_dir = self.config_root / "gupload"
        self.config_dir.mkdir(parents=True)
        (self.config_dir / "config.json").write_text(json.dumps({
            "owner": "offline-owner", "repo": "offline-repo", "branch": "main",
            "public_repo": False, "collision_policy": "rename",
        }), encoding="utf-8")
        self.source_dir = self.root / "Riley's 音楽"
        self.source_dir.mkdir()
        self.source = self.source_dir / "file's cover.png"
        self.source.write_bytes(b"offline image bytes")
        self.environ = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config_root)})
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def test_offline_plan_handles_apostrophes_unicode_destination_and_names(self):
        result = {}
        output = StringIO()
        with patch.object(menu, "confirm_exact", return_value=False), redirect_stdout(output):
            self.assertEqual(menu._plan_and_execute(
                [str(self.source)], names=["café 'cover'.png"], path="artists/Riley's 音楽",
                collision="rename", formats=["mdimage", "literal"],
            ), 0)
            result = dict(menu._LAST_PLAN)
        item = result["items"][0]
        self.assertEqual(item["source"], str(self.source))
        self.assertEqual(item["filename"], "café 'cover'.png")
        self.assertEqual(item["remote_path"], "uploads/artists/Riley's 音楽/café 'cover'.png")
        self.assertEqual(item["collision"], "rename")
        self.assertEqual(item["formats"], ["mdimage", "literal"])
        self.assertIn("Offline plan saved", output.getvalue())
        self.assertEqual(gupload.read_history(), [])

    def test_template_application_changes_real_offline_plan(self):
        template = {
            "name_pattern": "{category}-{stem}.{ext}",
            "path": "artists/Riley's 音楽",
            "collision": "update",
            "formats": ["mdimage"],
        }
        with patch.object(menu, "confirm_exact", return_value=False), redirect_stdout(StringIO()):
            self.assertEqual(menu.apply_template(template, [str(self.source)]), 0)
        planned = menu._LAST_PLAN["items"][0]
        self.assertEqual(planned["filename"], "images-file's cover.png")
        self.assertEqual(planned["remote_path"], "uploads/artists/Riley's 音楽/images-file's cover.png")
        self.assertEqual(planned["collision"], "update")
        self.assertEqual(planned["formats"], ["mdimage"])
        self.assertEqual(gupload.read_history(), [])

    def test_explicit_template_pattern_overrides_preset_pattern(self):
        config_file = self.config_dir / "config.json"
        config = json.loads(config_file.read_text(encoding="utf-8"))
        config["presets"] = {
            "routed": {
                "path": "artists/routed",
                "name_pattern": "preset-{stem}.{ext}",
            }
        }
        config_file.write_text(json.dumps(config), encoding="utf-8")
        template = {
            "preset": "routed",
            "name_pattern": "template-{stem}.{ext}",
        }
        with patch.object(menu, "confirm_exact", return_value=False), redirect_stdout(StringIO()):
            self.assertEqual(menu.apply_template(template, [str(self.source)]), 0)
        item = menu._LAST_PLAN["items"][0]
        self.assertEqual(item["filename"], "template-file's cover.png")
        self.assertEqual(item["remote_path"], "uploads/artists/routed/template-file's cover.png")

    def test_relative_execute_filename_is_treated_as_local_source(self):
        unusual = self.root / "--execute"
        unusual.write_bytes(b"not a flag")
        with patch("os.getcwd", return_value=str(self.root)), \
             patch.object(menu, "confirm_exact", return_value=False), \
             redirect_stdout(StringIO()):
            self.assertEqual(menu._plan_and_execute(["--execute", str(self.source)]), 0)
        sources = [item["source"] for item in menu._LAST_PLAN["items"]]
        self.assertEqual(sources, [str(unusual), str(self.source)])
        self.assertTrue(all(Path(source).is_absolute() for source in sources))
        self.assertEqual(gupload.read_history(), [])

    def test_flag_looking_custom_name_remains_filename_data(self):
        with patch.object(menu, "confirm_exact", return_value=False), redirect_stdout(StringIO()):
            self.assertEqual(menu._plan_and_execute([str(self.source)], names=["--execute"]), 0)
        self.assertEqual(menu._LAST_PLAN["items"][0]["filename"], "--execute.png")
        self.assertEqual(gupload.read_history(), [])

    def test_invalid_saved_template_pattern_is_reported_without_traceback(self):
        output = StringIO()
        with patch.object(menu, "_templates", return_value={"bad": {"name_pattern": "{unknown}"}}), \
             patch.object(menu, "choose", side_effect=["a", "q"]), \
             patch.object(menu, "ask", return_value="bad"), \
             patch.object(menu, "collect_upload_inputs", return_value=[str(self.source)]), \
             redirect_stdout(output):
            menu._template_menu()
        self.assertIn("Cannot apply template", output.getvalue())

    def test_directory_inputs_expand_before_custom_name_count_validation(self):
        second = self.source_dir / "second.png"
        second.write_bytes(b"second image")
        names = ["first custom.png", "second custom.png"]
        with patch.object(menu, "confirm_exact", return_value=False), redirect_stdout(StringIO()):
            self.assertEqual(menu._plan_and_execute([str(self.source_dir)], names=names), 0)
        self.assertEqual([item["filename"] for item in menu._LAST_PLAN["items"]], names)

    def test_cancel_and_empty_input_never_execute_or_mutate_history(self):
        with patch.object(menu, "confirm_exact", return_value=False), \
             patch.object(gupload, "execute_plan", side_effect=AssertionError("cancelled plan executed")), \
             redirect_stdout(StringIO()):
            self.assertEqual(menu._plan_and_execute([""]), 0)
            self.assertEqual(menu._plan_and_execute([str(self.source)]), 0)
        self.assertEqual(gupload.read_history(), [])

    def test_queue_keeps_partial_failure_retryable_and_planned_pending(self):
        queue = [
            {"source": str(self.root / "ok"), "status": "pending"},
            {"source": str(self.root / "bad"), "status": "pending"},
            {"source": str(self.root / "planned"), "status": "pending"},
            {"source": str(self.root / "old"), "status": "completed"},
        ]
        menu.queue_results(queue, [item["source"] for item in queue[:3]], {
            "items": [
                {"source": str(self.root / "ok"), "status": "succeeded"},
                {"source": str(self.root / "bad"), "status": "failed", "error": "offline"},
                {"source": str(self.root / "planned"), "status": "planned"},
            ],
            "errors": ["offline"],
        })
        self.assertEqual([item["status"] for item in queue], ["completed", "failed", "pending", "completed"])

    def test_config_and_logs_redact_secrets(self):
        self.assertEqual(menu._redact({"nested": {"github_token": "secret-value", "owner": "riley"}}),
                         {"nested": {"github_token": "[REDACTED]", "owner": "riley"}})
        rendered = menu._redact_log("Authorization: Bearer abc token=xyz owner=riley")
        self.assertNotIn("abc", rendered)
        self.assertNotIn("xyz", rendered)
        self.assertIn("owner=riley", rendered)


if __name__ == "__main__":
    unittest.main()
