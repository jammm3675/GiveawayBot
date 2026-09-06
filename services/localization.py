from database import db
import locales.en.main_menu
import locales.en.game_menu
import locales.en.wallet
import locales.en.giveaway
import locales.en.otc_market
import locales.en.notifications
import locales.en.admin
import locales.en.common
import locales.en.store
import locales.en.september_wl

import locales.ru.main_menu
import locales.ru.game_menu
import locales.ru.wallet
import locales.ru.giveaway
import locales.ru.otc_market
import locales.ru.notifications
import locales.ru.admin
import locales.ru.common
import locales.ru.store
import locales.ru.september_wl

def get_locale_by_lang(lang: str):
    # Base English texts
    texts = {}
    modules = [
        locales.en.main_menu,
        locales.en.game_menu,
        locales.en.wallet,
        locales.en.giveaway,
        locales.en.otc_market,
        locales.en.notifications,
        locales.en.admin,
        locales.en.common,
        locales.en.store,
        locales.en.september_wl,
    ]

    for module in modules:
        texts.update(module.TEXTS)

    if lang == 'ru':
        ru_modules = [
            locales.ru.main_menu,
            locales.ru.game_menu,
            locales.ru.wallet,
            locales.ru.giveaway,
            locales.ru.otc_market,
            locales.ru.notifications,
            locales.ru.admin,
            locales.ru.common,
            locales.ru.store,
            locales.ru.september_wl,
        ]
        for module in ru_modules:
            texts.update(module.TEXTS)

    return texts

async def get_locale(user_id: int):
    lang = await db.get_user_language(user_id)
    return get_locale_by_lang(lang)
