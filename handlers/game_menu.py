import asyncio
import os
import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
import html

from database import db
from services.leaderboard import LeaderboardService
from services.referral_service import ReferralService
from services.points_service import PointsService
from services.holder_service import HolderService
from utils import safe_edit_text, normalize_wallet, short_wallet
from services.localization import get_locale

logger = logging.getLogger(__name__)
router = Router()

async def show_game_menu(message: types.Message | types.CallbackQuery, state: FSMContext, texts: dict):
    user_id = message.from_user.id
    # texts from middleware

    # Parallelize independent DB calls
    points_data, refs = await asyncio.gather(
        db.get_points(user_id),
        db.get_referral_count(user_id)
    )

    if not points_data:
        await PointsService.recalculate_points(user_id)
        points_data = await db.get_points(user_id)

    rp = points_data.get("total_points", 0) if points_data else 0

    text = texts["game_menu_title"].format(rp=rp, refs=refs)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["highscore_btn"], callback_data="leaderboard", icon_custom_emoji_id="5258330865674494479")
    builder.button(text=texts["boost_btn"], callback_data="boost_menu", icon_custom_emoji_id="5260221883940347555")
    builder.button(text=texts["referral_btn"], callback_data="referral_menu", icon_custom_emoji_id="6032594876506312598")
    builder.button(text=texts["login_btn"], callback_data="wallet_menu", icon_custom_emoji_id="5258204546391351475")
    builder.button(text=texts["store_btn"], callback_data="store_menu", icon_custom_emoji_id="5983399041197675256")
    builder.button(text=texts["september_wl_btn"], callback_data="september_wl")
    builder.button(text=texts["game_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 1, 1)

    if isinstance(message, types.CallbackQuery):
        await safe_edit_text(message, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "game_menu")
async def game_menu_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_game_menu(callback, state, texts)

@router.callback_query(F.data == "referral_menu")
async def referral_menu_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware

    results = await asyncio.gather(
        ReferralService.get_or_create_ref_code(user_id),
        callback.bot.get_me(),
        db.get_points(user_id),
        db.get_referral_count(user_id)
    )
    ref_code, bot_user, points_data, total_invited = results
    ref_link = f"https://t.me/{bot_user.username}?start=ref_{ref_code}"
    active_refs = points_data.get("active_referrals", 0) if points_data else 0

    text = texts["referral_menu_title"].format(
        ref_link=f"<code>{ref_link}</code>",
        invited=total_invited,
        active=active_refs
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "leaderboard")
async def leaderboard_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware

    # Use points table for leaderboard
    top_points = await db.get_leaderboard(limit=10)

    lines = []
    for i, p in enumerate(top_points, 1):
        # Data from joined users table
        user_data = p.get("users") or {}
        uname = user_data.get("username")
        fname = user_data.get("first_name")
        tid = p.get("user_id")

        if uname:
            final_name = f"@{html.escape(uname)}"
        elif fname:
            final_name = html.escape(fname)
        else:
            final_name = f"<code>{tid}</code>"
        rp = p.get("total_points", 0)
        packs = p.get("packs", 0)
        active_refs = p.get("active_referrals", 0)
        lines.append(f"┋ {i}. {final_name} — {rp} RP ({packs}/{active_refs})")

    user_points = await db.get_points(user_id)
    user_pos_line = ""

    if user_points:
        try:
            rank_res = await db.client.rpc("get_user_rank", {"user_id_param": user_id}).execute()
            rank = rank_res.data if rank_res.data else "—"
        except:
            rank = "—"

        user_data = user_points.get("users") or {}
        uname = user_data.get("username")
        fname = user_data.get("first_name")

        if uname:
            final_name = f"@{html.escape(uname)}"
        elif fname:
            final_name = html.escape(fname)
        else:
            final_name = f"<code>{user_id}</code>"
        rp = user_points.get("total_points", 0)
        packs = user_points.get("packs", 0)
        active_refs = user_points.get("active_referrals", 0)
        user_pos_line = f"┋ {rank}. {final_name} — {rp} RP ({packs}/{active_refs})"

    text = texts["game_leaderboard_title"].format(
        lines='\n'.join(lines),
        user_pos=user_pos_line
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "holders_chat")
async def holders_chat_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware

    # Verify holder status via HolderService
    await HolderService.verify_holder_status(user_id)

    # Get packs from points table
    points_data = await db.get_points(user_id)
    packs = points_data.get("packs", 0) if points_data else 0

    text = texts["holders_chat_title"].format(packs=packs)

    builder = InlineKeyboardBuilder()
    builder.button(text="ACCESS CHAT", callback_data="check_holders_chat_access")
    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "check_holders_chat_access")
async def check_holders_chat_access(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    user_id = callback.from_user.id
    # texts from middleware

    # Get packs from points table
    points_data = await db.get_points(user_id)
    packs = points_data.get("packs", 0) if points_data else 0

    if packs < 10:
        await callback.answer(texts["need_packs_msg"], show_alert=True)
        return

    # Access granted
    await callback.answer(texts["access_granted_msg"], show_alert=True)

    # Replace button with actual join link
    otc_chat_id = os.environ.get("OTC_CHAT_ID")
    try:
        expire_date = datetime.now() + timedelta(hours=24)
        invite = await bot.create_chat_invite_link(
            chat_id=otc_chat_id,
            member_limit=1,
            expire_date=expire_date,
            creates_join_request=False
        )

        # Save to database
        await db.save_holder_invite(
            telegram_id=user_id,
            username=callback.from_user.username,
            packs=packs
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="JOIN CHAT", url=invite.invite_link)
        builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
        builder.adjust(1)

        await safe_edit_text(callback, texts["holders_chat_join_success"], reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

    except Exception as e:
        logger.error(f"Error creating invite link: {e}")
        await callback.answer(texts["holders_chat_error"], show_alert=True)

@router.callback_query(F.data == "join_holders_chat")
async def join_holders_chat_handler(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    await check_holders_chat_access(callback, state, bot)
