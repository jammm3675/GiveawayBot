import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import aiohttp

import loader
from database import db
from utils import normalize_to_raw, raw_to_user_friendly


logger = logging.getLogger(__name__)

NOTAPES_COLLECTION = "EQDwLDJcRXegHyvvRHXouGrUODuF0eagnWzLvUMUSTw8tv3Y"
GETGEMS_BASE_URL = "https://api.getgems.io/public-api"
WL_APES_PER_PLACE = 4
CACHE_TTL = timedelta(minutes=10)
MAX_PAGES = 100


class GetgemsUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class WlSnapshot:
    nft_count: int
    wl_count: int
    checked_at: datetime
    stale: bool = False


def _as_utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def fetch_notapes_count(wallet_address: str) -> int:
    api_key = os.getenv("GETGEMS_API_KEY", "").strip()
    if not api_key:
        raise GetgemsUnavailableError("GETGEMS_API_KEY is not configured")

    api_wallet = raw_to_user_friendly(wallet_address)
    url = (
        f"{GETGEMS_BASE_URL}/nft/collection/items/"
        f"{quote(NOTAPES_COLLECTION, safe='')}/{quote(api_wallet, safe='')}"
    )
    headers = {"accept": "application/json", "Authorization": api_key}
    cursor = None
    seen_cursors: set[str] = set()
    nft_addresses: set[str] = set()
    collection_raw = normalize_to_raw(NOTAPES_COLLECTION)

    session = loader.http_session
    owns_session = session is None or session.closed
    if owns_session:
        session = aiohttp.ClientSession()
    try:
        for _ in range(MAX_PAGES):
            params = {"limit": 100}
            if cursor:
                params["after"] = cursor
            try:
                async with session.get(url, headers=headers, params=params, timeout=15) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise GetgemsUnavailableError(
                            f"Getgems returned HTTP {response.status}: {body[:160]}"
                        )
                    payload = await response.json()
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise GetgemsUnavailableError("Getgems request failed") from exc

            if not payload.get("success") or not isinstance(payload.get("response"), dict):
                raise GetgemsUnavailableError("Getgems returned an invalid response")
            result = payload["response"]
            items = result.get("items") or []
            if not isinstance(items, list):
                raise GetgemsUnavailableError("Getgems items payload is invalid")

            for item in items:
                if not isinstance(item, dict):
                    continue
                item_collection = item.get("collectionAddress")
                if item_collection and normalize_to_raw(str(item_collection)) != collection_raw:
                    continue
                address = item.get("address")
                if address:
                    nft_addresses.add(normalize_to_raw(str(address)))

            next_cursor = result.get("cursor")
            if not next_cursor:
                return len(nft_addresses)
            cursor = str(next_cursor)
            if cursor in seen_cursors:
                raise GetgemsUnavailableError("Getgems returned a repeated cursor")
            seen_cursors.add(cursor)
    finally:
        if owns_session:
            await session.close()

    raise GetgemsUnavailableError("Getgems pagination limit exceeded")


async def get_wl_snapshot(user_id: int, wallet_address: str, profile: dict) -> WlSnapshot:
    now = datetime.now(timezone.utc)
    checked_at = _as_utc(profile.get("september_wl_checked_at"))
    cached_count = profile.get("september_wl_nft_count")
    checked_wallet = profile.get("september_wl_checked_wallet")
    cache_matches_wallet = (
        checked_wallet
        and normalize_to_raw(str(checked_wallet)) == normalize_to_raw(wallet_address)
    )
    if cache_matches_wallet and checked_at and cached_count is not None and now - checked_at < CACHE_TTL:
        count = max(0, int(cached_count))
        return WlSnapshot(count, count // WL_APES_PER_PLACE, checked_at)

    try:
        count = await fetch_notapes_count(wallet_address)
    except GetgemsUnavailableError:
        if cache_matches_wallet and checked_at and cached_count is not None:
            count = max(0, int(cached_count))
            return WlSnapshot(count, count // WL_APES_PER_PLACE, checked_at, stale=True)
        raise

    wl_count = count // WL_APES_PER_PLACE
    await db.update_user_fields(
        user_id,
        september_wl_nft_count=count,
        september_wl_count=wl_count,
        september_wl_checked_at=now,
        september_wl_checked_wallet=wallet_address,
    )
    return WlSnapshot(count, wl_count, now)
