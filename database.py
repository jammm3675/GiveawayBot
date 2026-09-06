import os
import logging
from typing import List, Optional, Dict, Any
from supabase import create_async_client, AsyncClient
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "").strip()
        self.key = os.environ.get("SUPABASE_KEY", "").strip()
        self.client: Optional[AsyncClient] = None

    async def connect(self):
        if not self.url or not self.key:
            logger.error("❌ SUPABASE_URL or SUPABASE_KEY is missing!")
            return
        try:
            self.client = await create_async_client(self.url, self.key)
            logger.info("✅ Supabase client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")

    def _check_client(self) -> bool:
        return self.client is not None

    async def track_chat(self, chat_id: int, title: str, chat_type: Optional[str] = None):
        if not self._check_client(): return
        try:
            data = {
                "chat_id": chat_id,
                "title": title
            }
            if chat_type:
                data["chat_type"] = chat_type
            await self.client.table("chats").upsert(data).execute()
        except Exception as e:
            logger.error(f"Error tracking chat: {e}")

    async def is_chat_tracked(self, chat_id: int) -> bool:
        if not self._check_client(): return False
        try:
            response = await self.client.table("chats").select("chat_id").eq("chat_id", chat_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking if chat is tracked: {e}")
            return False

    async def get_tracked_chats(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("chats").select("chat_id, title, chat_type").execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting tracked chats: {e}")
            return []

    async def get_tracked_groups(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("chats").select("chat_id, title, chat_type").in_("chat_type", ["group", "supergroup", "channel"]).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting tracked groups: {e}")
            return []

    async def create_giveaway(self, creator_id: int, chat_id: int, title: str, mode: str, value: Any, winners_count: int, prizes: List[str], end_at: Optional[datetime] = None, mandatory_channels: List[str] = [], allowed_users: Optional[List[str]] = None) -> Dict:
        if not self._check_client(): return {}
        try:
            data = {
                "creator_id": creator_id,
                "chat_id": chat_id,
                "title": title,
                "mode": mode,
                "value": str(value),
                "winners_count": winners_count,
                "prizes": prizes,
                "status": "pending",
                "end_at": end_at.isoformat() if end_at else None,
                "mandatory_channels": mandatory_channels,
                "allowed_users": allowed_users
            }
            response = await self.client.table("giveaways").insert(data).execute()
            return response.data[0]
        except Exception as e:
            logger.error(f"Error creating giveaway: {e}")
            return {}

    async def add_giveaway_message(self, giveaway_id: int, chat_id: int, message_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("giveaway_messages").upsert({
                "giveaway_id": giveaway_id,
                "chat_id": chat_id,
                "message_id": message_id
            }).execute()
        except Exception as e:
            logger.error(f"Error adding giveaway message: {e}")

    async def get_giveaway_messages(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaway_messages").select("chat_id, message_id").eq("giveaway_id", giveaway_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting giveaway messages: {e}")
            return []

    async def finish_giveaway(self, giveaway_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("giveaways").update({"status": "finished"}).eq("id", giveaway_id).execute()
        except Exception as e:
            logger.error(f"Error finishing giveaway: {e}")

    async def update_giveaway_status(self, giveaway_id: int, status: str):
        if not self._check_client(): return
        try:
            await self.client.table("giveaways").update({"status": status}).eq("id", giveaway_id).execute()
        except Exception as e:
            logger.error(f"Error updating giveaway status: {e}")

    async def get_expired_giveaways(self, now: datetime) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaways").select("id, creator_id, chat_id, title, winners_count, prizes, mandatory_channels, allowed_users").eq("status", "active").eq("mode", "timed").lte("end_at", now.isoformat()).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error fetching expired giveaways: {e}")
            return []

    async def get_giveaway(self, giveaway_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("giveaways").select("id, creator_id, chat_id, title, mode, value, winners_count, prizes, status, end_at, mandatory_channels, allowed_users").eq("id", giveaway_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting giveaway: {e}")
            return None

    async def add_participant(self, giveaway_id: int, user_id: int, username: Optional[str], tickets_used: int = 1) -> bool:
        if not self._check_client(): return False
        try:
            await self.ensure_user_exists(user_id)
            existing = await self.client.table("participants").select("id").eq("giveaway_id", giveaway_id).eq("user_id", user_id).execute()
            if existing.data:
                return False
            await self.client.table("participants").insert({
                "giveaway_id": giveaway_id,
                "user_id": user_id,
                "username": username,
                "tickets_used": tickets_used
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Error adding participant: {e}")
            return False

    async def remove_participant(self, giveaway_id: int, user_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("participants").delete().eq("giveaway_id", giveaway_id).eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"Error removing participant: {e}")

    async def get_participants(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("participants").select("user_id, username, tickets_used").eq("giveaway_id", giveaway_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting participants: {e}")
            return []

    async def get_user_created_giveaways(self, user_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaways").select("*, chats(title)").eq("creator_id", user_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting user created giveaways: {e}")
            return []

    async def save_winners(self, giveaway_id: int, winners: List[Dict]):
        if not self._check_client(): return
        try:
            data = []
            for w in winners:
                data.append({
                    "giveaway_id": giveaway_id,
                    "user_id": w['user_id'],
                    "username": w['username'],
                    "prize": w['prize']
                })
            if data:
                await self.client.table("winners").insert(data).execute()
        except Exception as e:
            logger.error(f"Error saving winners: {e}")

    async def get_giveaway_winners(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("winners").select("user_id, username, prize").eq("giveaway_id", giveaway_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting giveaway winners: {e}")
            return []

    async def get_setting(self, key: str) -> Optional[str]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("settings").select("value").eq("key", key).execute()
            return response.data[0]["value"] if response.data else None
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return None

    async def update_setting(self, key: str, value: str):
        if not self._check_client(): return
        try:
            await self.client.table("settings").upsert({"key": key, "value": value}).execute()
        except Exception as e:
            logger.error(f"Error updating setting {key}: {e}")

    async def upsert_notification(self, data: dict):
        if not self._check_client(): return
        try:
            await self.client.table("notifications").upsert(data).execute()
        except Exception as e:
            logger.error(f"Error upserting notification: {e}")

    async def get_notifications(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("notifications").select("id, title, text, custom_buttons, interval_minutes, is_active, last_sent, last_message_id, chat_id").execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return []

    async def get_active_notifications(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("notifications").select("id, title, text, custom_buttons, interval_minutes, last_sent, last_message_id, chat_id").eq("is_active", True).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting active notifications: {e}")
            return []

    async def update_notification_stats(self, notification_id: int, last_sent: Any, last_message_id: int):
        """
        Обновляет статистику отправки уведомления.
        Имя метода и аргументы приведены в соответствие с вызовом в handlers/completion.py.
        Новые столбцы в БД не создаются — используются существующие 'last_sent' и 'last_message_id'.
        """
        if not self._check_client(): return
        try:
            # Приводим datetime к формату ISO строки для Supabase
            iso_sent = last_sent.isoformat() if hasattr(last_sent, 'isoformat') else str(last_sent)

            await self.client.table("notifications") \
                .update({
                    "last_sent": iso_sent,
                    "last_message_id": last_message_id
                }) \
                .eq("id", notification_id) \
                .execute()
            logger.info(f"✅ Статистика уведомления {notification_id} успешно обновлена в БД.")
        except Exception as e:
            logger.error(f"❌ Ошибка при вызове update_notification_stats для ID {notification_id}: {e}")

            # РЕЗЕРВНЫЙ ВАРИАНТ (Анти-спам): Если запись last_message_id упала из-за типов данных,
            # принудительно обновляем ХОТЯ БЫ время отправки, чтобы бот не спамил каждую минуту.
            try:
                await self.client.table("notifications") \
                    .update({"last_sent": datetime.now().isoformat()}) \
                    .eq("id", notification_id) \
                    .execute()
                logger.warning(f"⚠️ Время отправки уведомления {notification_id} зафиксировано без message_id.")
            except Exception as inner_e:
                logger.error(f"🚨 Полный отказ Supabase при попытке спасти ситуацию: {inner_e}")

    # --- NEW METHODS ---

    async def get_latest_snapshot(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("snapshots")                 .select("data")                 .order("created_at", desc=True)                 .limit(1)                 .execute()
            return response.data[0]["data"] if response.data else []
        except Exception as e:
            logger.error(f"Error getting latest snapshot: {e}")
            return []

    async def save_snapshot(self, data: List[Dict], snapshot_type: str = "daily", total_held: Optional[int] = None, milestone: Optional[int] = None):
        if not self._check_client(): return
        try:
            payload = {
                "data": data,
                "snapshot_type": snapshot_type,
                "total_held": total_held,
                "milestone": milestone
            }
            await self.client.table("snapshots").insert(payload).execute()
        except Exception as e:
            logger.error(f"Error saving snapshot: {e}")

    async def milestone_exists(self, milestone: int) -> bool:
        if not self._check_client(): return False
        try:
            response = await self.client.table("snapshots") \
                .select("id") \
                .eq("snapshot_type", "milestone") \
                .eq("milestone", milestone) \
                .limit(1) \
                .execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking milestone existence: {e}")
            return False
    async def get_milestones_data(self) -> list[dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("snapshots") \
                .select("data, milestone") \
                .eq("snapshot_type", "milestone") \
                .in_("milestone", [333, 666, 1000]) \
                .order("milestone", desc=False) \
                .execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting milestones data: {e}")
            return []

    async def get_last_total_held(self) -> Optional[int]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("snapshots") \
                .select("total_held") \
                .not_.is_("total_held", "null") \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            return response.data[0]["total_held"] if response.data else None
        except Exception as e:
            logger.error(f"Error getting last total held: {e}")
            return None

    async def cleanup_old_snapshots(self, days: int = 14):
        if not self._check_client(): return
        try:
            threshold = (datetime.now() - timedelta(days=days)).isoformat()
            await self.client.table("snapshots").delete().lt("created_at", threshold).execute()
        except Exception as e:
            logger.error(f"Error cleaning up snapshots: {e}")

    async def get_user_wallet(self, telegram_id: int) -> Optional[str]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("users").select("wallet_address").eq("telegram_id", telegram_id).execute()
            return response.data[0]["wallet_address"] if response.data else None
        except Exception as e:
            logger.error(f"Error getting user wallet: {e}")
            return None

    async def get_september_wl_profile(self, telegram_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("users").select(
                "telegram_id,username,first_name,wallet_address,ethereum_wallet,"
                "ethereum_wallet_updated_at,september_wl_nft_count,"
                "september_wl_count,september_wl_checked_at,september_wl_checked_wallet"
            ).eq("telegram_id", telegram_id).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error("Error getting September WL profile: %s", e)
            return None

    async def ensure_user_exists(self, telegram_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("users").upsert({"telegram_id": telegram_id}).execute()
        except Exception as e:
            logger.error(f"Error ensuring user exists: {e}")

    async def update_user_wallet(self, telegram_id: int, wallet_address: Optional[str]):
        if not self._check_client(): return
        try:
            await self.client.table("users").upsert({
                "telegram_id": telegram_id,
                "wallet_address": wallet_address
            }).execute()
        except Exception as e:
            logger.error(f"Error updating user wallet: {e}")

    async def get_all_linked_wallets(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("users").select("telegram_id, wallet_address").not_.is_("wallet_address", "null").execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting all linked wallets: {e}")
            return []

    async def get_user_language(self, telegram_id: int) -> str:
        if not self._check_client(): return 'en'
        try:
            response = await self.client.table("users").select("language").eq("telegram_id", telegram_id).execute()
            if response.data and response.data[0].get("language"):
                return response.data[0]["language"]
            return 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return 'en'

    async def update_user_language(self, telegram_id: int, language: str):
        if not self._check_client(): return
        try:
            await self.client.table("users").upsert({
                "telegram_id": telegram_id,
                "language": language
            }).execute()
        except Exception as e:
            logger.error(f"Error updating user language: {e}")

    async def get_last_holder_invite(self, telegram_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("holders_chat_invites") \
                .select("telegram_id, packs, created_at") \
                .eq("telegram_id", telegram_id) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting last holder invite: {e}")
            return None

    async def save_holder_invite(self, telegram_id: int, username: Optional[str], packs: int):
        if not self._check_client(): return
        try:
            await self.client.table("holders_chat_invites").insert({
                "telegram_id": telegram_id,
                "username": username,
                "packs": packs
            }).execute()
        except Exception as e:
            logger.error(f"Error saving holder invite: {e}")

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("users").select("telegram_id, wallet_address, language, ref_code, referrer_id, referral_status, wallet_connected_at, referral_validated_at, terms_version, community_joined_at, username, first_name, og_bonus_awarded_at, og_bonus_amount, holder_verified_at, active_tickets").eq("telegram_id", telegram_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting user by telegram_id: {e}")
            return None

    async def is_community_joined(self, telegram_id: int) -> bool:
        if not self._check_client():
            return False

        try:
            response = (
                await self.client
                .table("users")
                .select("community_joined_at")
                .eq("telegram_id", telegram_id)
                .execute()
            )

            if not response.data:
                return False

            return bool(response.data[0].get("community_joined_at"))

        except Exception as e:
            logger.error(f"Error checking community status: {e}")
            return False

    async def mark_community_joined(self, telegram_id: int):
        await self.update_user_fields(
            telegram_id,
            community_joined_at=datetime.utcnow().isoformat()
        )

    async def get_user_by_ref_code(self, ref_code: str) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("users").select("telegram_id, username").eq("ref_code", ref_code).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting user by ref_code: {e}")
            return None

    async def update_user_fields(self, telegram_id: int, **kwargs) -> bool:
        if not self._check_client(): return False
        try:
            for key, value in kwargs.items():
                if isinstance(value, datetime):
                    kwargs[key] = value.isoformat()

            await self.client.table("users").update(kwargs).eq("telegram_id", telegram_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating user fields: {e}")
            return False

    async def create_referral(self, referrer_id: int, referred_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("referrals").upsert({
                "referrer_id": referrer_id,
                "referred_id": referred_id,
                "status": "new"
            }).execute()
        except Exception as e:
            logger.error(f"Error creating referral: {e}")

    async def update_referral_status(self, referred_id: int, status: str, activated_at: Optional[datetime] = None):
        if not self._check_client(): return
        try:
            data = {"status": status}
            if activated_at:
                data["activated_at"] = activated_at.isoformat()
            await self.client.table("referrals").update(data).eq("referred_id", referred_id).execute()
        except Exception as e:
            logger.error(f"Error updating referral status: {e}")

    async def get_points(self, user_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("points").select("*, users(username, first_name)").eq("user_id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting points: {e}")
            return None

    async def upsert_points(self, user_id: int, **kwargs):
        if not self._check_client(): return
        try:
            data = {"user_id": user_id, "updated_at": datetime.now().isoformat()}
            data.update(kwargs)
            await self.client.table("points").upsert(data).execute()
        except Exception as e:
            logger.error(f"Error upserting points: {e}")

    async def get_leaderboard(self, limit: int = 50) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("points").select("*, users(username, first_name)").order("total_points", desc=True).order("packs", desc=True).order("active_referrals", desc=True).order("user_id", desc=False).limit(limit).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return []



    async def get_referral_count(self, referrer_id: int) -> int:
        if not self._check_client(): return 0
        try:
            response = await self.client.table("referrals").select("id", count="exact").eq("referrer_id", referrer_id).execute()
            return response.count if response.count is not None else 0
        except Exception as e:
            logger.error(f"Error getting referral count: {e}")
            return 0

    async def get_points_batch(self, user_ids: List[int]) -> List[Dict]:
        if not self._check_client() or not user_ids: return []
        try:
            response = await self.client.table("points").select("*, users(username, first_name)").in_("user_id", user_ids).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting points batch: {e}")
            return []

    async def get_users_batch(self, telegram_ids: List[int]) -> List[Dict]:
        if not self._check_client() or not telegram_ids: return []
        try:
            response = await self.client.table("users").select("telegram_id, referrer_id").in_("telegram_id", telegram_ids).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting users batch: {e}")
            return []

    async def add_og_holder(self, telegram_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("og_holders_snapshot").upsert({
                "telegram_id": telegram_id
            }).execute()
        except Exception as e:
            logger.error(f"Error adding OG holder: {e}")

    async def get_og_snapshot_count(self) -> int:
        if not self._check_client(): return 0
        try:
            response = await self.client.table("og_holders_snapshot") \
                .select("telegram_id", count="exact") \
                .execute()
            return response.count if response.count is not None else 0
        except Exception as e:
            logger.error(f"Error getting OG snapshot count: {e}")
            return 0

    async def save_og_snapshot(self, telegram_ids: List[int]):
        if not self._check_client() or not telegram_ids: return
        try:
            data = [{"telegram_id": tid} for tid in telegram_ids]
            await self.client.table("og_holders_snapshot").upsert(data).execute()
        except Exception as e:
            logger.error(f"Error saving OG snapshot: {e}")

    async def get_all_registered_users(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            result = (
                await self.client
                .table("users")
                .select("telegram_id")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting all registered users: {e}")
            return []

    async def get_all_known_users(self) -> List[int]:
        """
        Gathers unique Telegram IDs from all tables where users might be tracked.
        """
        if not self._check_client(): return []
        try:
            # 1. users
            res_users = await self.client.table("users").select("telegram_id").execute()
            ids = {row["telegram_id"] for row in res_users.data} if res_users.data else set()

            # 2. participants
            res_parts = await self.client.table("participants").select("user_id").execute()
            if res_parts.data:
                ids.update(row["user_id"] for row in res_parts.data)

            # 3. points
            res_pts = await self.client.table("points").select("user_id").execute()
            if res_pts.data:
                ids.update(row["user_id"] for row in res_pts.data)

            # 4. referrals (referrer_id and referred_id)
            res_refs = await self.client.table("referrals").select("referrer_id, referred_id").execute()
            if res_refs.data:
                for row in res_refs.data:
                    if row.get("referrer_id"): ids.add(row["referrer_id"])
                    if row.get("referred_id"): ids.add(row["referred_id"])

            # 5. holders_chat_invites
            res_invs = await self.client.table("holders_chat_invites").select("telegram_id").execute()
            if res_invs.data:
                ids.update(row["telegram_id"] for row in res_invs.data)

            return list(ids)
        except Exception as e:
            logger.error(f"Error getting all known users: {e}")
            return []

    async def get_og_holder_ids(self) -> List[int]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("og_holders_snapshot").select("telegram_id").execute()
            return [row["telegram_id"] for row in response.data] if response.data else []
        except Exception as e:
            logger.error(f"Error getting OG holder IDs: {e}")
            return []

    async def is_og_holder(self, telegram_id: int) -> bool:
        if not self._check_client(): return False
        try:
            response = await self.client.table("og_holders_snapshot") \
                .select("telegram_id") \
                .eq("telegram_id", telegram_id) \
                .limit(1) \
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error checking OG holder status: {e}")
            return False


    async def add_active_tickets(self, user_id: int, amount: int):
        if not self._check_client(): return
        try:
            # We use RPC or raw SQL for increment if possible, but here we can just update
            user = await self.get_user_by_telegram_id(user_id)
            current = user.get("active_tickets", 0) if user else 0
            await self.client.table("users").update({"active_tickets": current + amount}).eq("telegram_id", user_id).execute()
        except Exception as e:
            logger.error(f"Error adding active tickets: {e}")

    async def reset_active_tickets(self, user_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("users").update({"active_tickets": 0}).eq("telegram_id", user_id).execute()
        except Exception as e:
            logger.error(f"Error resetting active tickets: {e}")

    async def add_spent_points(self, user_id: int, amount: int):
        if not self._check_client(): return
        try:
            points = await self.get_points(user_id)
            current = points.get("spent_points", 0) if points else 0
            await self.client.table("points").upsert({
                "user_id": user_id,
                "spent_points": current + amount,
                "updated_at": datetime.now().isoformat() # PostgREST handles now() in some contexts or we can use python
            }).execute()
        except Exception as e:
            logger.error(f"Error adding spent points: {e}")

    # --- Atomic store and giveaway operations ---

    @staticmethod
    def _rpc_payload(data: Any) -> Dict:
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return {}

    async def purchase_tickets_atomic(
        self,
        user_id: int,
        amount: int,
        unit_cost: int,
        idempotency_key: str,
    ) -> Dict:
        if not self._check_client():
            return {"ok": False, "error": "DATABASE_UNAVAILABLE"}
        try:
            response = await self.client.rpc("purchase_store_tickets", {
                "p_user_id": user_id,
                "p_amount": amount,
                "p_unit_cost": unit_cost,
                "p_idempotency_key": idempotency_key,
            }).execute()
            return self._rpc_payload(response.data)
        except Exception as e:
            logger.error(f"Atomic ticket purchase failed: {e}")
            return {"ok": False, "error": "PURCHASE_FAILED"}

    async def get_active_store_lots(self, limit: int = 20) -> List[Dict]:
        if not self._check_client():
            return []
        try:
            response = await self.client.table("store_lots") \
                .select("id, title, description, price_rp, total_quantity, sold_quantity, image_url, reward_type, reward_payload, per_user_limit, status, created_at") \
                .eq("status", "active") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting active store lots: {e}")
            return []

    async def get_store_lot(self, lot_id: int) -> Optional[Dict]:
        if not self._check_client():
            return None
        try:
            response = await self.client.table("store_lots") \
                .select("*") \
                .eq("id", lot_id) \
                .limit(1) \
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting store lot {lot_id}: {e}")
            return None

    async def purchase_store_lot_atomic(
        self,
        user_id: int,
        lot_id: int,
        idempotency_key: str,
    ) -> Dict:
        if not self._check_client():
            return {"ok": False, "error": "DATABASE_UNAVAILABLE"}
        try:
            response = await self.client.rpc("purchase_store_lot", {
                "p_user_id": user_id,
                "p_lot_id": lot_id,
                "p_idempotency_key": idempotency_key,
            }).execute()
            return self._rpc_payload(response.data)
        except Exception as e:
            logger.error(f"Atomic lot purchase failed: {e}")
            return {"ok": False, "error": "PURCHASE_FAILED"}

    async def create_store_lot(self, data: Dict) -> Optional[Dict]:
        if not self._check_client():
            return None
        try:
            response = await self.client.table("store_lots").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating store lot: {e}")
            return None

    async def get_store_lots_admin(self, limit: int = 30) -> List[Dict]:
        if not self._check_client():
            return []
        try:
            response = await self.client.table("store_lots") \
                .select("*") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting admin store lots: {e}")
            return []

    async def set_store_lot_status(self, lot_id: int, status: str) -> bool:
        if not self._check_client():
            return False
        try:
            if status == "active":
                lot = await self.get_store_lot(lot_id)
                if not lot or lot.get("sold_quantity", 0) >= lot.get("total_quantity", 0):
                    return False
            response = await self.client.table("store_lots") \
                .update({"status": status}) \
                .eq("id", lot_id) \
                .execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error updating store lot status: {e}")
            return False

    async def get_pending_store_purchases(self, limit: int = 30) -> List[Dict]:
        if not self._check_client():
            return []
        try:
            response = await self.client.table("store_purchases") \
                .select("id, lot_id, user_id, price_rp, status, created_at, store_lots(title)") \
                .eq("status", "paid") \
                .order("created_at", desc=False) \
                .limit(limit) \
                .execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting pending purchases: {e}")
            return []

    async def get_store_purchase(self, purchase_id: int) -> Optional[Dict]:
        if not self._check_client():
            return None
        try:
            response = await self.client.table("store_purchases") \
                .select("id, lot_id, user_id, price_rp, status, created_at, store_lots(title, reward_type, reward_payload), users(username, first_name)") \
                .eq("id", purchase_id) \
                .limit(1) \
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting store purchase {purchase_id}: {e}")
            return None

    async def fulfill_store_purchase(
        self,
        purchase_id: int,
        admin_id: int,
        note: str = "",
    ) -> Optional[Dict]:
        if not self._check_client():
            return None
        try:
            response = await self.client.table("store_purchases") \
                .update({
                    "status": "fulfilled",
                    "fulfilled_at": datetime.now().isoformat(),
                    "fulfilled_by": admin_id,
                    "fulfillment_note": note or None,
                }) \
                .eq("id", purchase_id) \
                .eq("status", "paid") \
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error fulfilling store purchase: {e}")
            return None

    async def join_giveaway_atomic(
        self,
        giveaway_id: int,
        user_id: int,
        username: Optional[str],
    ) -> Dict:
        if not self._check_client():
            return {"ok": False, "error": "DATABASE_UNAVAILABLE"}
        try:
            await self.ensure_user_exists(user_id)
            response = await self.client.rpc("join_giveaway_atomic", {
                "p_giveaway_id": giveaway_id,
                "p_user_id": user_id,
                "p_username": username,
            }).execute()
            return self._rpc_payload(response.data)
        except Exception as e:
            logger.error(f"Atomic giveaway join failed: {e}")
            return {"ok": False, "error": "JOIN_FAILED"}

    async def claim_giveaway_completion(self, giveaway_id: int) -> bool:
        if not self._check_client():
            return False
        try:
            response = await self.client.rpc("claim_giveaway_completion", {
                "p_giveaway_id": giveaway_id,
            }).execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error claiming giveaway completion: {e}")
            return False

    async def get_active_giveaways(self, limit: int = 20) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaways").select(
                "id,title,prizes,mode,value,end_at,status"
            ).eq("status", "active").order("id", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting active giveaways: {e}")
            return []

    async def get_giveaway_ticket_balance(self, giveaway_id: int, user_id: int) -> int:
        if not self._check_client(): return 1
        try:
            response = await self.client.table("giveaway_ticket_balances").select(
                "tickets,consumed_at"
            ).eq("giveaway_id", giveaway_id).eq("user_id", user_id).limit(1).execute()
            if not response.data:
                return 1
            return max(1, int(response.data[0].get("tickets", 1)))
        except Exception as e:
            logger.error(f"Error getting giveaway ticket balance: {e}")
            return 1

    async def get_giveaway_ticket_ranking(self, giveaway_id: int, user_id: int) -> Dict:
        if self._check_client():
            try:
                response = await self.client.rpc("get_giveaway_ticket_ranking", {
                    "p_giveaway_id": giveaway_id,
                    "p_user_id": user_id,
                }).execute()
                payload = self._rpc_payload(response.data)
                if isinstance(payload, dict) and "top" in payload:
                    return payload
            except Exception as e:
                logger.warning("Ticket ranking RPC unavailable, using fallback: %s", e)
        participants = await self.get_participants(giveaway_id)
        ordered = sorted(
            participants,
            key=lambda row: (-max(1, int(row.get("tickets_used") or 1)), int(row.get("user_id") or 0)),
        )
        user_rank = next(
            (index for index, row in enumerate(ordered, 1) if int(row.get("user_id")) == user_id),
            None,
        )
        return {"top": ordered[:10], "rank": user_rank, "count": len(ordered)}

    async def get_ticket_offers(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("ticket_offers").select(
                "code,ticket_count,price_rp,mode,pricing_mode,sort_order"
            ).eq("active", True).order("sort_order").execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting ticket offers: {e}")
            return []

    async def purchase_giveaway_tickets(self, user_id: int, giveaway_id: int,
                                         offer_code: str, idempotency_key: str) -> Dict:
        if not self._check_client(): return {"ok": False, "error": "DATABASE_UNAVAILABLE"}
        try:
            response = await self.client.rpc("purchase_giveaway_tickets", {
                "p_user_id": user_id, "p_giveaway_id": giveaway_id,
                "p_offer_code": offer_code, "p_idempotency_key": idempotency_key,
            }).execute()
            return self._rpc_payload(response.data)
        except Exception as e:
            logger.error(f"Error purchasing giveaway tickets: {e}")
            return {"ok": False, "error": "PURCHASE_FAILED"}

    async def claim_gram_deposit(self, payload: Dict) -> Dict:
        if not self._check_client(): return {"ok": False, "error": "DATABASE_UNAVAILABLE"}
        try:
            response = await self.client.rpc("claim_gram_deposit", payload).execute()
            return self._rpc_payload(response.data)
        except Exception as e:
            logger.error(f"Error claiming GRAM deposit: {e}")
            return {"ok": False, "error": "CLAIM_FAILED"}

    async def create_otc_listing(self, data: Dict) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("otc_listings").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating OTC listing: {e}")
            return None

    async def update_otc_listing(self, listing_id: int, data: Dict) -> bool:
        if not self._check_client(): return False
        try:
            response = await self.client.table("otc_listings").update(data).eq("id", listing_id).execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Error updating OTC listing: {e}")
            return False

    async def get_otc_listing(self, listing_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("otc_listings").select("*").eq("id", listing_id).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting OTC listing: {e}")
            return None

    async def create_otc_offer(self, data: Dict) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("otc_offers").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating OTC offer: {e}")
            return None

    async def get_otc_offer(self, offer_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("otc_offers").select(
                "*,otc_listings(item_name,item_url,price_text,trade_type)"
            ).eq("id", offer_id).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting OTC offer: {e}")
            return None

    async def respond_otc_offer(self, offer_id: int, seller_id: int, status: str) -> Dict:
        if not self._check_client(): return {"ok": False, "error": "DATABASE_UNAVAILABLE"}
        try:
            response = await self.client.rpc("respond_otc_offer", {
                "p_offer_id": offer_id, "p_seller_id": seller_id, "p_status": status,
            }).execute()
            return self._rpc_payload(response.data)
        except Exception as e:
            logger.error(f"Error responding to OTC offer: {e}")
            return {"ok": False, "error": "DATABASE_ERROR"}


db = Database()
