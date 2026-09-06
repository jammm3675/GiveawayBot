import asyncio
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import html
import logging
from datetime import datetime

from loader import bot
from database import db
from handlers.giveaway_creation import GiveawayCreation
from utils import is_admin, is_any_admin, safe_answer, safe_edit_text, is_holder
from services.localization import get_locale
from services.referral_service import ReferralService
from services.points_service import PointsService
from services.getgems_service import get_collection_stats
from config import ADMIN_IDS

logger = logging.getLogger(__name__)
router = Router()

class OnboardingStates(StatesGroup):
    SELECT_LANGUAGE = State()
    CHECK_COMMUNITY = State()

REQUIRED_COMMUNITIES = [
    "@notapes",
    "@notapeschat"
]

async def get_main_menu_keyboard(user_id: int, texts: dict, is_holder_res: bool = None):
    builder = InlineKeyboardBuilder()
    
    if user_id in ADMIN_IDS:
        # Row 1
        builder.button(text=texts["game_btn"], callback_data="game_menu", icon_custom_emoji_id="5258508428212445001")
        builder.button(text=texts["otc_btn"], callback_data="otc_market", icon_custom_emoji_id="5260687681733533075")

        # Row 2
        builder.button(text=texts["giveaway_btn"], callback_data="create_giveaway", icon_custom_emoji_id="5296348778012361146")
        builder.button(text=texts["history_btn"], callback_data="history_created", icon_custom_emoji_id="5257969839313526622")

        # Row 3
        builder.button(text=texts["notifications_btn"], callback_data="manage_notifications", icon_custom_emoji_id="5260325873688518261")
        builder.button(text=texts["update_gif_btn"], callback_data="admin_update_gif", icon_custom_emoji_id="5257974976094412956")

        # Row 4
        builder.button(text=texts["language_btn"], callback_data="select_language", icon_custom_emoji_id="5260512129240276089")
        builder.button(text=texts["rules_btn"], callback_data="show_rules", icon_custom_emoji_id="5258328383183396223")
        builder.button(text=texts["chat_btn"], url="https://t.me/notapeschat", icon_custom_emoji_id="5258513401784573443", style="success")
        builder.button(text=texts["support_btn"], url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522", style="primary")
        builder.adjust(2, 2, 2, 2, 2)
    elif is_holder_res if is_holder_res is not None else await is_holder(user_id):
        builder.button(text=texts["game_btn"], callback_data="game_menu", icon_custom_emoji_id="5258508428212445001")
        builder.button(text=texts["otc_btn"], callback_data="otc_market", icon_custom_emoji_id="5260687681733533075")
        builder.button(text=texts["language_btn"], callback_data="select_language", icon_custom_emoji_id="5260512129240276089")
        builder.button(text=texts["rules_btn"], callback_data="show_rules", icon_custom_emoji_id="5258328383183396223")
        builder.button(text=texts["chat_btn"], url="https://t.me/notapeschat", icon_custom_emoji_id="5258513401784573443", style="success")
        builder.button(text=texts["support_btn"], url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522", style="primary")
        builder.adjust(2, 2, 2)

    else:
        builder.button(text=texts["game_btn"], callback_data="game_menu", icon_custom_emoji_id="5258508428212445001")
        builder.button(text=texts["rules_btn"], callback_data="show_rules", icon_custom_emoji_id="5258328383183396223")
        builder.button(text=texts["language_btn"], callback_data="select_language", icon_custom_emoji_id="5260512129240276089")
        builder.button(text=texts["chat_btn"], url="https://t.me/notapeschat", icon_custom_emoji_id="5258513401784573443", style="success")
        builder.button(text=texts["support_btn"], url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522", style="primary")
        builder.adjust(1, 2, 2)

    return builder.as_markup()


def get_community_keyboard(texts: dict):
    builder = InlineKeyboardBuilder()

    builder.button(
        text=texts["join_notapes_btn"],
        url="https://t.me/notapes"
    )

    builder.button(
        text=texts["join_notapes_chat_btn"],
        url="https://t.me/notapeschat"
    )

    builder.button(
        text=texts["check_join_btn"],
        callback_data="check_community"
    )

    builder.adjust(1)

    return builder.as_markup()

async def show_community_screen(
    event: types.Message | types.CallbackQuery,
    texts: dict
):
    text = texts["community_screen_text"]
    keyboard = get_community_keyboard(texts)

    if isinstance(event, types.Message):
        await safe_answer(
            event,
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_edit_text(
            event,
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

async def is_member(chat_id: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(
            chat_id,
            user_id
        )

        return member.status in {
            "member",
            "administrator",
            "creator"
        }

    except Exception:
        return False

async def validate_community(user_id: int) -> bool:
    for community in REQUIRED_COMMUNITIES:

        ok = await is_member(
            community,
            user_id
        )

        if not ok:
            return False

    return True

async def show_rules_screen(
    event: types.Message | types.CallbackQuery,
    texts: dict
):
    text = texts["rules_screen_text"]

    builder = InlineKeyboardBuilder()

    builder.button(
        text=texts["terms_btn"],
        url="https://telegra.ph/%E3%81%A3-NOTAPES--LEGAL-PROTOCOLS-06-11",
        icon_custom_emoji_id="5258477770735885832"
    )
    builder.button(
        text=texts["privacy_btn"],
        url="https://telegra.ph/%E3%81%A3--NOTAPES--LEGAL-PROTOCOLS-06-11-3",
        icon_custom_emoji_id="5260249440450520061"
    )
    builder.button(
        text=texts["referral_rules_btn"],
        url="https://telegra.ph/%E3%81%A3--NOTAPES--REFERRAL-PROTOCOL-06-11",
        icon_custom_emoji_id="5258513401784573443"
    )
    builder.button(
        text=texts["giveaway_rules_btn"],
        url="https://telegra.ph/%E3%81%A3--NOTAPES--TOURNAMENT-PROTOCOL-06-11",
        icon_custom_emoji_id="5258093637450866522"
    )
    builder.button(
        text=texts["continue_btn"],
        callback_data="accept_terms",
        icon_custom_emoji_id="5260416304224936047"
    )

    builder.adjust(2, 2, 1)

    if isinstance(event, types.Message):
        await safe_answer(
            event,
            text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_edit_text(
            event,
            text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )

async def build_main_menu_text(texts: dict, stats: dict = None):
    if not stats: stats = await get_collection_stats()
    return texts["main_menu_text"].format(
        floor=stats["floor"],
        volume=stats["volume"]
    )

async def show_main_menu_message(message: types.Message, texts: dict):
    user_id = message.from_user.id

    # Parallelize independent operations
    is_holder_task = is_holder(user_id)
    stats_task = get_collection_stats()

    is_holder_res, stats = await asyncio.gather(
        is_holder_task,
        stats_task
    )

    keyboard = await get_main_menu_keyboard(user_id, texts, is_holder_res=is_holder_res)
    menu_text = await build_main_menu_text(texts, stats=stats)

    await safe_answer(
        message,
        menu_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

async def show_main_menu_callback(callback: types.CallbackQuery, texts: dict):
    user_id = callback.from_user.id

    # Parallelize independent operations
    is_holder_task = is_holder(user_id)
    stats_task = get_collection_stats()

    is_holder_res, stats = await asyncio.gather(
        is_holder_task,
        stats_task
    )

    keyboard = await get_main_menu_keyboard(user_id, texts, is_holder_res=is_holder_res)
    menu_text = await build_main_menu_text(texts, stats=stats)

    await safe_edit_text(
        callback,
        menu_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@router.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext, texts: dict):
    user_id = message.from_user.id
    # texts provided by middleware

    # 1 & 2. Parallelize user registration and profile sync
    await asyncio.gather(
        db.ensure_user_exists(user_id),
        PointsService.update_username(user_id, message.from_user.username, message.from_user.first_name)
    )

    # 3. Process referral parameter
    deep_link = command.args if command.args and (
        command.args == "september_wl"
        or command.args.startswith(("lot_", "giveaway_", "offer_"))
    ) else None
    if deep_link:
        await state.update_data(pending_deep_link=deep_link)
    elif command.args:
        await ReferralService.process_start_param(user_id, command.args)

    # 4. Ensure user has a referral code (First Login Migration)
    await ReferralService.get_or_create_ref_code(user_id)

    # 5. Check Terms (Parallelized)
    policy_res, user_data = await asyncio.gather(
        db.get_setting("Privacy Policy"),
        db.get_user_by_telegram_id(user_id)
    )
    current_policy_version = policy_res or "v1"
    user_terms_version = user_data.get("terms_version") if user_data else None

    logger.info(
        f"Policy check: user={user_terms_version}, current={current_policy_version}"
    )

    if not user_data or user_terms_version != current_policy_version:
        # Start onboarding flow
        await state.set_state(OnboardingStates.SELECT_LANGUAGE)
        await show_language_selection(message, texts)
        return

    # 5.5 Check Community
    community_joined = bool(user_data.get("community_joined_at"))
    if not community_joined:
        await state.set_state(OnboardingStates.CHECK_COMMUNITY)
        await show_community_screen(message, texts)
        return

    # 6. Open a requested entity after all access checks, otherwise main menu.
    if deep_link:
        await dispatch_deep_link(message, deep_link, state, texts)
    else:
        await show_main_menu_message(message, texts)


async def dispatch_deep_link(message: types.Message | types.CallbackQuery, payload: str, state: FSMContext, texts: dict):
    async def fallback():
        if isinstance(message, types.CallbackQuery):
            await show_main_menu_callback(message, texts)
        else:
            await show_main_menu_message(message, texts)
    if payload == "september_wl":
        await state.update_data(pending_deep_link=None)
        from handlers.september_wl import show_september_wl
        await show_september_wl(message, state, texts)
        return
    try:
        kind, raw_id = payload.rsplit("_", 1)
        entity_id = int(raw_id)
    except (ValueError, AttributeError):
        await fallback()
        return
    await state.update_data(pending_deep_link=None)
    if kind == "lot":
        from handlers.store import show_lot_detail
        await show_lot_detail(message, entity_id, texts, state)
    elif kind == "giveaway":
        from handlers.store import show_giveaway_tickets
        await show_giveaway_tickets(message, entity_id, texts, state)
    elif kind == "offer":
        from handlers.otc_market import start_offer_from_link
        await start_offer_from_link(message, entity_id, state, texts)
    else:
        await fallback()


@router.callback_query(F.data == "check_community")
async def check_community_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    texts: dict
):
    user_id = callback.from_user.id

    joined = await validate_community(
        user_id
    )

    if not joined:
        await callback.answer(
            texts["community_not_joined_alert"],
            show_alert=True
        )
        return

    await db.mark_community_joined(
        user_id
    )

    pending = (await state.get_data()).get("pending_deep_link")
    await state.clear()
    if pending:
        await state.update_data(pending_deep_link=pending)

    await show_rules_screen(
        callback,
        texts
    )

@router.callback_query(F.data == "accept_terms")
async def accept_terms_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts provided by middleware

    current_policy_version = await db.get_setting("Privacy Policy") or "v1"

    # Save acceptance
    await db.update_user_fields(
        user_id,
        terms_accepted_at=datetime.now().isoformat(),
        terms_version=current_policy_version
    )

    logger.info(f"User {user_id} accepted terms {current_policy_version}")

    pending = (await state.get_data()).get("pending_deep_link")
    if pending:
        await dispatch_deep_link(callback, pending, state, texts)
    else:
        await show_main_menu_callback(callback, texts)

@router.message(Command("setup"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_setup(message: types.Message, texts: dict):
    # texts from middleware
    if await is_admin(message.chat.id, message.from_user.id):
        await db.track_chat(message.chat.id, message.chat.title, message.chat.type)
        safe_title = html.escape(message.chat.title)
        await safe_answer(
            message,
            texts["setup_success"].format(title=safe_title),
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_answer(message, texts["setup_admin_only"], parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await state.clear()
    await show_main_menu_callback(callback, texts)

@router.callback_query(F.data == "create_giveaway")
async def create_giveaway_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    # texts from middleware
    await callback.answer()
    chats = await db.get_tracked_groups()
    if not chats:
        await safe_edit_text(callback, texts["no_groups_available"], parse_mode=ParseMode.HTML)
        return

    admin_chats = []
    for chat in chats:
        if await is_admin(chat['chat_id'], callback.from_user.id):
            admin_chats.append(chat)

    if not admin_chats:
        await callback.answer(texts["no_admin_rights"], show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for chat in admin_chats:
        builder.button(text=chat['title'], callback_data=f"chat_{chat['chat_id']}")
    builder.button(text=texts["giveaway_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    msg = await safe_edit_text(callback, texts["select_group_giveaway"], reply_markup=builder.as_markup())
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(GiveawayCreation.SELECT_CHAT)

async def show_language_selection(event: types.Message | types.CallbackQuery, texts: dict):
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇸 English", callback_data="set_lang_en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.adjust(1)

    if isinstance(event, types.Message):
        await safe_answer(
            event,
            texts["select_language"],
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_edit_text(
            event,
            texts["select_language"],
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )

@router.callback_query(F.data == "select_language")
async def select_language_handler(callback: types.CallbackQuery, texts: dict):
    await callback.answer()
    # texts from middleware
    await show_language_selection(callback, texts)

@router.callback_query(F.data == "show_rules")
async def show_rules_callback(callback: types.CallbackQuery, texts: dict):
    await callback.answer()
    # texts from middleware
    await show_rules_screen(callback, texts)

@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    lang = callback.data.replace("set_lang_", "")
    await db.update_user_language(callback.from_user.id, lang)

        # Reload texts
    from services.localization import get_locale_by_lang
    texts = get_locale_by_lang(lang)

    # Check if we are in onboarding flow
    current_state = await state.get_state()
    if current_state == OnboardingStates.SELECT_LANGUAGE:
        await state.set_state(OnboardingStates.CHECK_COMMUNITY)
        await show_community_screen(callback, texts)
        return
    else:
        await callback.answer(texts["giveaway_success_msg"])
        await show_main_menu_callback(callback, texts)
