import asyncio
import os
import tempfile
import unittest

import database
from xui_api import XUIApi


class _FakeAsyncClient:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class ResourceAndRetentionTests(unittest.TestCase):
    def test_xui_api_context_closes_http_client(self):
        api = XUIApi("http://panel.example", "user", "password")
        original_client = api.client
        fake_client = _FakeAsyncClient()
        api.client = fake_client

        async def use_api():
            async with api:
                pass

        try:
            asyncio.run(use_api())
            self.assertTrue(fake_client.closed)
        finally:
            asyncio.run(original_client.aclose())

    def test_cleanup_keeps_the_configured_retention_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_dir, old_path = database.DB_DIR, database.DB_PATH
            database.DB_DIR = temp_dir
            database.DB_PATH = os.path.join(temp_dir, "traffic.db")
            try:
                database.init_db()
                database.batch_record_traffic([
                    ("panel", "old", 1, 1, 100, 0, "2025-08-16"),
                    ("panel", "kept", 1, 1, 100, 0, "2025-08-17"),
                    ("panel", "new", 1, 1, 100, 0, "2026-08-16"),
                ])

                deleted = database.cleanup_old_traffic(
                    retention_days=365, reference_date="2026-08-16"
                )

                self.assertEqual(deleted, 1)
                self.assertEqual(
                    database.get_date_range(), ("2025-08-17", "2026-08-16")
                )
            finally:
                database.DB_DIR, database.DB_PATH = old_dir, old_path


if __name__ == "__main__":
    unittest.main()
