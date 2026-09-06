import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import loader
from services import september_wl_service as service


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return str(self.payload)


class FakeSession:
    closed = False

    def __init__(self, pages):
        self.pages = iter(pages)
        self.params = []

    def get(self, _url, **kwargs):
        self.params.append(kwargs["params"])
        return FakeResponse(next(self.pages))


class SeptemberWlTests(unittest.IsolatedAsyncioTestCase):
    async def test_getgems_pagination_and_collection_filter(self):
        pages = [
            {"success": True, "response": {"items": [
                {"address": "0:aaa", "collectionAddress": service.NOTAPES_COLLECTION, "actualOwnerAddress": "0:user"},
                {"address": "0:bad", "collectionAddress": "0:wrong"},
                {"address": "0:other", "collectionAddress": service.NOTAPES_COLLECTION, "actualOwnerAddress": "0:other"},
            ], "cursor": "next"}},
            {"success": True, "response": {"items": [
                {"address": "0:bbb", "collectionAddress": service.NOTAPES_COLLECTION},
            ], "cursor": None}},
        ]
        fake = FakeSession(pages)
        old_session = loader.http_session
        old_key = os.environ.get("GETGEMS_API_KEY")
        loader.http_session = fake
        os.environ["GETGEMS_API_KEY"] = "test-key"
        try:
            self.assertEqual(await service.fetch_notapes_count("0:user"), 2)
            self.assertEqual(fake.params, [{"limit": 100}, {"limit": 100, "after": "next"}])
        finally:
            loader.http_session = old_session
            if old_key is None:
                os.environ.pop("GETGEMS_API_KEY", None)
            else:
                os.environ["GETGEMS_API_KEY"] = old_key

    async def test_recent_database_snapshot_uses_cache(self):
        now = datetime.now(timezone.utc)
        profile = {
            "september_wl_nft_count": 11,
            "september_wl_checked_at": (now - timedelta(minutes=2)).isoformat(),
            "september_wl_checked_wallet": "0:user",
        }
        snapshot = await service.get_wl_snapshot(1, "0:user", profile)
        self.assertEqual(snapshot.nft_count, 11)
        self.assertEqual(snapshot.wl_count, 2)
        self.assertFalse(snapshot.stale)

    async def test_missing_api_key_fails_cleanly(self):
        old_key = os.environ.pop("GETGEMS_API_KEY", None)
        try:
            with self.assertRaises(service.GetgemsUnavailableError):
                await service.fetch_notapes_count("0:user")
        finally:
            if old_key is not None:
                os.environ["GETGEMS_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
