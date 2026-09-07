from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from combatai.alias_store import record_pending_alias


class AliasStoreTests(unittest.TestCase):
    def test_new_alias_is_null(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_aliases.json"
            self.assertTrue(record_pending_alias("Contact R C Rescue", path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"contact r c rescue": None})

    def test_existing_reviewed_mapping_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pending_aliases.json"
            path.write_text('{"contact rescue": "Contact Air Sea Rescue"}\n', encoding="utf-8")
            self.assertFalse(record_pending_alias("Contact rescue", path))
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"contact rescue": "Contact Air Sea Rescue"},
            )


if __name__ == "__main__":
    unittest.main()
