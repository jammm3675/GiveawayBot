import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db
from services.september_wl_service import GetgemsUnavailableError, get_wl_snapshot
from services.ui_cleanup import MessageCategory, remember_message
from utils import safe_answer, safe_edit_text, short_wallet


router = Router()
ETH_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class SeptemberWlStates(StatesGroup):
    ENTER_ETH_WALLET = State()


def _short_eth(address: str | None) -> str:
    return f"{address[:8]}…{address[-6:]}" if address else "—"


async def show_september_wl(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
    texts: dict,
):
    user_id = event.from_user.id
    await db.ensure_user_exists(user_id)
    profile = await db.get_september_wl_profile(user_id) or {}
    ton_wallet = profile.get("wallet_address")
    snapshot = None
    api_error = False
    if ton_wallet:
        try:
            snapshot = await get_wl_snapshot(user_id, ton_wallet, profile)
        except GetgemsUnavailableError:
            api_error = True

    if snapshot:
        status = texts["september_wl_eligible"].format(count=snapshot.wl_count) \
            if snapshot.wl_count else texts["september_wl_not_eligible"]
        checked = snapshot.checked_at.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M MSK")
        cache_note = texts["september_wl_stale"] if snapshot.stale else ""
        nft_count = snapshot.nft_count
        wl_count = snapshot.wl_count
    else:
        status = texts["september_wl_api_error"] if api_error else texts["september_wl_connect_hint"]
        checked = "—"
        cache_note = ""
        nft_count = "—"
        wl_count = "—"

    builder = InlineKeyboardBuilder()
    if ton_wallet:
        builder.button(text=texts["september_wl_check_btn"], callback_data="september_wl_refresh")
    else:
        builder.button(
            text=texts["september_wl_connect_btn"],
            callback_data="september_wl_connect",
            icon_custom_emoji_id="5258204546391351475",
        )
    builder.button(
        text=texts["september_wl_eth_change_btn"] if profile.get("ethereum_wallet") else texts["september_wl_eth_add_btn"],
        callback_data="september_wl_eth",
    )
    builder.button(
        text=texts["game_back_btn"], callback_data="game_menu",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)

    text = texts["september_wl_title"].format(
        telegram_id=user_id,
        username=html.escape(f"@{event.from_user.username}" if event.from_user.username else "—"),
        ton_wallet=html.escape(short_wallet(ton_wallet)) if ton_wallet else "—",
        eth_wallet=html.escape(_short_eth(profile.get("ethereum_wallet"))),
        nft_count=nft_count,
        wl_count=wl_count,
        checked=checked,
        status=status,
        cache_note=cache_note,
    )
    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        msg = await safe_answer(event, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        await remember_message(state, msg, category=MessageCategory.TEMPORARY)


@router.callback_query(F.data == "september_wl")
async def september_wl_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await state.clear()
    await show_september_wl(callback, state, texts)


@router.callback_query(F.data == "september_wl_refresh")
async def september_wl_refresh(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer(texts["september_wl_cache_notice"])
    await show_september_wl(callback, state, texts)


@router.callback_query(F.data == "september_wl_connect")
async def september_wl_connect(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await state.update_data(wallet_return_callback="september_wl")
    from handlers.wallet import connect_wallet
    await connect_wallet(callback, state, texts)


@router.callback_query(F.data == "september_wl_eth")
async def september_wl_eth(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await state.set_state(SeptemberWlStates.ENTER_ETH_WALLET)
    await state.update_data(september_wl_prompt_id=callback.message.message_id)
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["game_back_btn"], callback_data="september_wl")
    await safe_edit_text(
        callback, texts["september_wl_eth_prompt"],
        reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state,
    )


@router.message(SeptemberWlStates.ENTER_ETH_WALLET, F.text)
async def save_september_wl_eth(message: types.Message, state: FSMContext, texts: dict):
    address = message.text.strip()
    state_data = await state.get_data()
    prompt_id = state_data.get("september_wl_prompt_id")
    try:
        await message.delete()
    except Exception:
        pass
    if not ETH_WALLET_RE.fullmatch(address):
        if prompt_id:
            builder = InlineKeyboardBuilder()
            builder.button(text=texts["game_back_btn"], callback_data="september_wl")
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=prompt_id,
                    text=f"{texts['september_wl_eth_prompt']}\n\n{texts['september_wl_eth_invalid']}",
                    reply_markup=builder.as_markup(),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        return

    await db.ensure_user_exists(message.from_user.id)
    saved = await db.update_user_fields(
        message.from_user.id,
        ethereum_wallet=address,
        ethereum_wallet_updated_at=datetime.now(timezone.utc).isoformat(),
    )
    if not saved:
        await safe_answer(message, texts["september_wl_save_error"], parse_mode=ParseMode.HTML)
        return
    if prompt_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except Exception:
            pass
    await state.clear()
    await show_september_wl(message, state, texts)
