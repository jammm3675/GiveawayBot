from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

def wallet_menu_keyboard(is_connected: bool, texts: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_connected:
        builder.button(text=texts["wallet_disconnect_btn"], callback_data="disconnect_wallet", icon_custom_emoji_id="5260342697075416641")
    else:
        builder.button(text=texts["wallet_connect_btn"], callback_data="connect_wallet", icon_custom_emoji_id="5316612764427367709")

    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    return builder.as_markup()

def wallet_selection_keyboard(available_wallets: list, texts: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for w in available_wallets:
        builder.button(text=w['name'].upper(), callback_data=f"select_wallet_{w['name']}")
    builder.button(text=texts["game_back_btn"], callback_data="wallet_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    return builder.as_markup()

def wallet_connect_keyboard(url: str, texts: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["wallet_open_wallet_btn"], url=url, icon_custom_emoji_id="5258204546391351475")
    builder.button(text=texts["wallet_cancel_btn"], callback_data="wallet_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    return builder.as_markup()

def wallet_success_keyboard(
    texts: dict,
    callback_data: str = "game_menu",
    button_text: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=button_text or texts["wallet_game_menu_btn"],
        callback_data=callback_data,
        icon_custom_emoji_id="5258508428212445001",
    )
    builder.adjust(1)
    return builder.as_markup()
