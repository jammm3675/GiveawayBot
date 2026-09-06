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
TONCENTER_NFT_URL = "https://toncenter.com/api/v3/nft/items"
WL_APES_PER_PLACE = 4
CACHE_TTL = timedelta(minutes=10)
MAX_PAGES = 100
TONCENTER_PAGE_SIZE = 1000


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


async def _fetch_getgems_count(wallet_address: str) -> int:
    api_key = os.getenv("GETGEMS_API_KEY", "").strip()
    if not api_key:
        raise GetgemsUnavailableError("GETGEMS_API_KEY is not configured")

    api_wallet = raw_to_user_friendly(wallet_address)
    url = (
        f"{GETGEMS_BASE_URL}/v1/nfts/collection/"
        f"{quote(NOTAPES_COLLECTION, safe='')}/owner/{quote(api_wallet, safe='')}"
    )
    headers = {"accept": "application/json", "Authorization": api_key}
    cursor = None
    seen_cursors: set[str] = set()
    nft_addresses: set[str] = set()
    collection_raw = normalize_to_raw(NOTAPES_COLLECTION)
    wallet_raw = normalize_to_raw(wallet_address)

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
                if not item_collection or normalize_to_raw(str(item_collection)) != collection_raw:
                    continue
                actual_owner = item.get("actualOwnerAddress") or item.get("ownerAddress")
                if actual_owner and normalize_to_raw(str(actual_owner)) != wallet_raw:
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


async def _fetch_toncenter_count(wallet_address: str) -> int:
    """Fallback for when the paid Getgems API is not configured or unavailable."""
    wallet_raw = normalize_to_raw(wallet_address)
    collection_raw = normalize_to_raw(NOTAPES_COLLECTION)
    nft_addresses: set[str] = set()

    session = loader.http_session
    owns_session = session is None or session.closed
    if owns_session:
        session = aiohttp.ClientSession()
    try:
        for page in range(MAX_PAGES):
            params = {
                "owner_address": wallet_raw,
                "collection_address": collection_raw,
                "include_on_sale": "true",
                "limit": TONCENTER_PAGE_SIZE,
                "offset": page * TONCENTER_PAGE_SIZE,
            }
            try:
                async with session.get(
                    TONCENTER_NFT_URL,
                    headers={"accept": "application/json"},
                    params=params,
                    timeout=15,
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise GetgemsUnavailableError(
                            f"TON Center returned HTTP {response.status}: {body[:160]}"
                        )
                    payload = await response.json()
            except (aiohttp.ClientError, TimeoutError) as exc:
                raise GetgemsUnavailableError("TON Center request failed") from exc

            items = payload.get("nft_items")
            if not isinstance(items, list):
                raise GetgemsUnavailableError("TON Center returned an invalid response")

            for item in items:
                if not isinstance(item, dict):
                    continue
                if normalize_to_raw(str(item.get("collection_address") or "")) != collection_raw:
                    continue
                owner = item.get("real_owner") or item.get("owner_address")
                if not owner or normalize_to_raw(str(owner)) != wallet_raw:
                    continue
                address = item.get("address")
                if address:
                    nft_addresses.add(normalize_to_raw(str(address)))

            if len(items) < TONCENTER_PAGE_SIZE:
                return len(nft_addresses)
    finally:
        if owns_session:
            await session.close()

    raise GetgemsUnavailableError("TON Center pagination limit exceeded")


async def fetch_notapes_count(wallet_address: str) -> int:
    """Count NOTAPES via Getgems, with a public chain indexer as a fallback."""
    getgems_error = None
    if os.getenv("GETGEMS_API_KEY", "").strip():
        try:
            return await _fetch_getgems_count(wallet_address)
        except GetgemsUnavailableError as exc:
            getgems_error = exc
            logger.warning("Getgems NOTAPES check failed; trying TON Center: %s", exc)
    else:
        logger.warning("GETGEMS_API_KEY is not configured; using TON Center for NOTAPES")

    try:
        count = await _fetch_toncenter_count(wallet_address)
        logger.info("NOTAPES count obtained from TON Center fallback: %s", count)
        return count
    except GetgemsUnavailableError as toncenter_error:
        logger.warning(
            "NOTAPES providers unavailable (Getgems=%s; TON Center=%s)",
            getgems_error or "not configured",
            toncenter_error,
        )
        raise GetgemsUnavailableError("All NOTAPES providers are unavailable") from toncenter_error


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
