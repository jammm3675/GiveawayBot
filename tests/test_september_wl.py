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
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
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
            self.assertTrue(all(
                "/v1/nfts/collection/" in url and "/owner/" in url
                for url in fake.urls
            ))
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

    async def test_missing_getgems_key_uses_toncenter(self):
        old_key = os.environ.pop("GETGEMS_API_KEY", None)
        pages = [{"nft_items": [
            {
                "address": "0:aaa",
                "collection_address": service.NOTAPES_COLLECTION,
                "real_owner": "0:user",
            },
            {
                "address": "0:other",
                "collection_address": service.NOTAPES_COLLECTION,
                "real_owner": "0:other",
            },
        ]}]
        fake = FakeSession(pages)
        old_session = loader.http_session
        loader.http_session = fake
        try:
            self.assertEqual(await service.fetch_notapes_count("0:user"), 1)
            self.assertEqual(fake.params[0]["limit"], 1000)
            self.assertEqual(fake.params[0]["offset"], 0)
        finally:
            loader.http_session = old_session
            if old_key is not None:
                os.environ["GETGEMS_API_KEY"] = old_key

    async def test_getgems_error_uses_toncenter(self):
        pages = [
            {"error": "invalid key"},
            {"nft_items": []},
        ]
        fake = FakeSession(pages)
        old_session = loader.http_session
        old_key = os.environ.get("GETGEMS_API_KEY")
        loader.http_session = fake
        os.environ["GETGEMS_API_KEY"] = "invalid-key"
        original_get = fake.get

        def get_with_getgems_error(url, **kwargs):
            if "getgems.io" in url:
                fake.urls.append(url)
                fake.params.append(kwargs["params"])
                return FakeResponse(next(fake.pages), status=401)
            return original_get(url, **kwargs)

        fake.get = get_with_getgems_error
        try:
            self.assertEqual(await service.fetch_notapes_count("0:user"), 0)
        finally:
            loader.http_session = old_session
            if old_key is None:
                os.environ.pop("GETGEMS_API_KEY", None)
            else:
                os.environ["GETGEMS_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
