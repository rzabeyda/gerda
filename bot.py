import asyncio
import logging
import random
import re
import time

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions, ChatMemberUpdated
from aiogram.enums import ChatMemberStatus

import config
import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

ALLOWED_LINKS = [
    "memstroybot", "memstroy_bot",
    "memstroy_chat",
    "memstroy_community",
]

LINK_PATTERN = re.compile(
    r"(https?://\S+|t\.me/\S+|@\w+)",
    re.IGNORECASE
)

BAD_WORD_REACTIONS = [
    "Ах ты школотрончик! Маме расскажу 😤",
    "Рот помой с мылом! 🧼 Герда всё видит 👀",
    "О-о-о, какие слова знаем! Мама в курсе? 😏",
    "Цензура включена! Бип-бип-бип 🤖",
    "Такие слова только взрослые говорят, а ты точно взрослый? 🍼",
    "Герда краснеет от стыда за тебя 😳",
    "Фильтруй базар, дружочек 🫧",
    "Воспитание где? Потерял? 📦",
    "Ой всё, иди в угол подумай о своём поведении 🙄",
    "Такие слова — это для слабаков. Ты же не слабак? 😬",
]

SHAME_RANKS = [
    "🤡 Додик",
    "👶 Маменькин сынок",
    "🧴 Тюбик",
    "💩 Обкаканый",
    "🐔 Кукарека-нарушитель",
    "🗑️ Мусорный бак",
    "🐛 Червячок позорный",
    "🤧 Сопля залётная",
    "🦆 Утёнок без мамы",
    "🥴 Путаник великий",
    "🧸 Плюшевый хулиган",
    "🐒 Обезьянка балованная",
]

MENTION_REPLIES = [
    "Какого тут школотрончика мне опустить? 😈",
    "Я здесь, я всё вижу, я всё помню 👁️",
    "Звали? Герда всегда на посту! 🫡",
    "Чё надо? 😒 Шучу, шучу, привет! 😄",
    "Тихо! Герда думает... Ладно, не думает, просто сидит 🪑",
    "Опять я? Ну ладно, слушаю 👂",
    "Вы вообще без меня не можете, да? 😏",
    "Герда тут! И она немного сердитая сегодня 😤",
    "Звали великую и ужасную Герду? 👑",
    "О, меня упомянули! Это лучший момент дня 🥹",
    "Чего хотели? Автограф? Селфи? 📸",
    "Я слежу за каждым из вас... особенно за тобой 😈",
    "Герда онлайн! Все нарушители — бегите 🏃",
    "Позвали? А то я тут скучала и ела печеньки 🍪",
    "Ку-ку! Герда из кустов наблюдает 🌿👀",
]

AUTO_MESSAGES = [
    "Эй, тут вообще кто-нибудь есть? Герда скучает 👀",
    "Тишина... Может обсудим что-нибудь интересное? 🤔",
    "Чат заснул? Герда будит всех метлой! 🧹",
    "А ну-ка, кто первый напишет? Герда ждёт! 😄",
    "Факт дня: пингвины — единственные птицы, которые умеют плавать, но не летать 🐧",
    "Вопрос дня: если бы вы могли путешествовать в любое место прямо сейчас — куда? ✈️",
    "Топ активности скоро обновится... Есть претенденты на первое место? 🏆",
    "Герда проверяет связь... Приём! Приём! Есть кто живой? 📡",
    "Ладно, раз все молчат — Герда сама поговорит. Привет, Герда! — Привет! 😅",
    "Тихо как в библиотеке... Только здесь можно орать 😂",
    "Народ, ну вы чего? Герда одна тут сидит, скучает, чай пьёт ☕",
    "Кто последний напишет — тот и виноват! 😈",
    "Герда объявляет конкурс на самое смешное сообщение! Призы воображаемые 🎁",
]

_last_auto_sent: int = 0

SHAME_HOURS = 6  # часов действует позорное прозвище


def display_name(user) -> str:
    row = db.get_user(user.id)
    if row:
        nick = db.get_active_nickname(row)
        if nick:
            return nick
    return user.full_name or user.username or str(user.id)


def display_name_from_row(row) -> str:
    nick = db.get_active_nickname(row)
    if nick:
        return nick
    return row["full_name"] or row["username"] or str(row["user_id"])


def contains_bad_word(text: str) -> bool:
    text_lower = text.lower()
    for word in config.BAD_WORDS:
        if word in text_lower:
            return True
    return False


def contains_forbidden_link(text: str) -> bool:
    matches = LINK_PATTERN.findall(text)
    for match in matches:
        match_lower = match.lower()
        allowed = False
        for white in ALLOWED_LINKS:
            if white in match_lower:
                allowed = True
                break
        if not allowed:
            return True
    return False


async def mute_user(chat_id: int, user_id: int, seconds: int = 300):
    until = int(time.time()) + seconds
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )
    except Exception as e:
        logging.error(f"Ошибка мута: {e}")


async def warn_user_bad(message: Message, user, mute_seconds: int = 300) -> int:
    warns = db.add_warning(user.id)
    name = display_name(user)
    reaction = random.choice(BAD_WORD_REACTIONS)
    shame = random.choice(SHAME_RANKS)

    if warns >= config.WARN_LIMIT:
        await message.reply(
            f"{reaction}\n\n"
            f"⛔ <b>{name}</b>, это уже {warns}/{config.WARN_LIMIT} предупреждений!\n"
            f"Мут на 5 минут! Новый титул на {SHAME_HOURS} часов: <b>{shame}</b> 🎭",
            parse_mode="HTML"
        )
        db.set_shame_nickname(user.id, shame, hours=SHAME_HOURS)
        await mute_user(message.chat.id, user.id, mute_seconds)
        db.reset_warnings(user.id)
    else:
        remaining = config.WARN_LIMIT - warns
        await message.reply(
            f"{reaction}\n\n"
            f"⚠️ <b>{name}</b>, предупреждение {warns}/{config.WARN_LIMIT}.\n"
            f"Ещё {remaining} — и получишь титул <b>{shame}</b> на {SHAME_HOURS} часов + мут 🤫",
            parse_mode="HTML"
        )
    return warns


async def warn_user(message: Message, user, reason: str, mute_seconds: int = 300) -> int:
    warns = db.add_warning(user.id)
    name = display_name(user)

    if warns >= config.WARN_LIMIT:
        shame = random.choice(SHAME_RANKS)
        await message.reply(
            f"⛔ <b>{name}</b>, {reason}\n"
            f"Предупреждений: {warns}/{config.WARN_LIMIT} — мут на 5 минут!\n"
            f"Новый титул на {SHAME_HOURS} часов: <b>{shame}</b> 🎭",
            parse_mode="HTML"
        )
        db.set_shame_nickname(user.id, shame, hours=SHAME_HOURS)
        await mute_user(message.chat.id, user.id, mute_seconds)
        db.reset_warnings(user.id)
    else:
        remaining = config.WARN_LIMIT - warns
        await message.reply(
            f"⚠️ <b>{name}</b>, {reason}\n"
            f"Предупреждение {warns}/{config.WARN_LIMIT}. Ещё {remaining} — и мут 🤫",
            parse_mode="HTML"
        )
    return warns


@dp.chat_member()
async def on_new_member(event: ChatMemberUpdated):
    if event.new_chat_member.status not in (
        ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED
    ):
        return
    if event.old_chat_member.status not in (
        ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.BANNED
    ):
        return

    user = event.new_chat_member.user
    db.upsert_user(user.id, user.username or "", user.full_name or "")

    greetings = [
        f"О, к нам пожаловал(а) <b>{user.full_name}</b>! 🎉 Добро пожаловать! Пиши смелее 😄",
        f"Встречайте — <b>{user.full_name}</b> теперь с нами! 👋 Не стесняйся, знакомься!",
        f"<b>{user.full_name}</b> зашёл(зашла) в чат. Герда уже знает о тебе всё 👀😈",
        f"Эй, <b>{user.full_name}</b>! Добро пожаловать в банду 😎 Правила читай у Герды /help",
    ]
    await bot.send_message(event.chat.id, random.choice(greetings), parse_mode="HTML")


# ══ КОМАНДЫ ══

@dp.message(Command("mystats"))
async def cmd_mystats(message: Message):
    user = message.from_user
    row = db.get_user(user.id)
    if not row:
        await message.reply("Я тебя ещё не знаю, напиши что-нибудь в чат сначала 😊")
        return

    rank = db.get_rank(row["messages"])
    next_rank, left = db.get_next_rank(row["messages"])
    name = display_name(user)
    nick = db.get_active_nickname(row)
    nick_display = nick if nick else "нет"

    # Показываем когда слетит позорное прозвище
    shame_line = ""
    if nick and row["nickname_expires_at"]:
        expires_in = row["nickname_expires_at"] - int(time.time())
        if expires_in > 0:
            hours_left = expires_in // 3600
            mins_left = (expires_in % 3600) // 60
            shame_line = f"\n⏳ Позорный титул слетит через: <b>{hours_left}ч {mins_left}м</b>"

    next_line = f"\n📈 До следующего ранга: <b>{left}</b> сообщений ({next_rank})" if next_rank else "\n🏆 Ты на максимальном ранге!"

    await message.reply(
        f"📊 <b>Статистика {name}</b>\n\n"
        f"🏅 Ранг: <b>{rank}</b>\n"
        f"💬 Сообщений: <b>{row['messages']}</b>\n"
        f"⚠️ Предупреждений: <b>{row['warnings']}</b>\n"
        f"🎭 Прозвище: <b>{nick_display}</b>"
        f"{shame_line}"
        f"{next_line}",
        parse_mode="HTML"
    )


@dp.message(Command("top"))
async def cmd_top(message: Message):
    users = db.get_top_users(10)
    if not users:
        await message.reply("Пока никого нет в базе 🤷")
        return

    lines = ["🏆 <b>Топ активных участников</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = display_name_from_row(row)
        rank = db.get_rank(row["messages"])
        lines.append(f"{medal} <b>{name}</b> — {row['messages']} сообщ. | {rank}")

    await message.reply("\n".join(lines), parse_mode="HTML")


@dp.message(Command("setnick"))
async def cmd_setnick(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.reply("Только администраторы могут давать прозвища 🔒")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.reply("Использование: /setnick @username Прозвище")
        return

    target_mention = args[1]
    nickname = args[2].strip()

    with db.get_conn() as conn:
        username_clean = target_mention.lstrip("@")
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username_clean,)
        ).fetchone()

    if not row:
        await message.reply(f"Пользователь {target_mention} не найден в базе 🤔")
        return

    db.set_nickname(row["user_id"], nickname, expires_at=0)  # постоянное
    await message.reply(
        f"✅ <b>{row['full_name']}</b> теперь называется <b>{nickname}</b> 🎭",
        parse_mode="HTML"
    )


@dp.message(Command("mynick"))
async def cmd_mynick(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("Использование: /mynick Твоё прозвище")
        return

    nickname = args[1].strip()
    if len(nickname) > 32:
        await message.reply("Прозвище слишком длинное, максимум 32 символа 😅")
        return

    db.upsert_user(message.from_user.id, message.from_user.username or "", message.from_user.full_name or "")
    db.set_nickname(message.from_user.id, nickname, expires_at=0)  # постоянное
    await message.reply(f"✅ Теперь тебя зовут <b>{nickname}</b> 🎭", parse_mode="HTML")


@dp.message(Command("warn"))
async def cmd_warn(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.reply("Только администраторы 🔒")
        return
    if not message.reply_to_message:
        await message.reply("Ответь на сообщение пользователя командой /warn")
        return

    target = message.reply_to_message.from_user
    await warn_user(message, target, "получил(а) предупреждение от администратора 👮", 600)


@dp.message(Command("unwarn"))
async def cmd_unwarn(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.reply("Только администраторы 🔒")
        return
    if not message.reply_to_message:
        await message.reply("Ответь на сообщение пользователя")
        return

    target = message.reply_to_message.from_user
    db.reset_warnings(target.id)
    name = display_name(target)
    await message.reply(f"✅ Предупреждения <b>{name}</b> сброшены", parse_mode="HTML")


@dp.message(Command("unmute"))
async def cmd_unmute(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.reply("Только администраторы 🔒")
        return
    if not message.reply_to_message:
        await message.reply("Ответь на сообщение пользователя командой /unmute")
        return

    target = message.reply_to_message.from_user
    name = display_name(target)
    try:
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        db.reset_warnings(target.id)
        await message.reply(f"✅ <b>{name}</b> размучен(а)! Надеюсь, исправился(ась) 😏", parse_mode="HTML")
    except Exception as e:
        await message.reply(f"Ошибка: {e}")


@dp.message(Command("ranks"))
async def cmd_ranks(message: Message):
    lines = ["🏅 <b>Ранговая система Герды</b>\n"]
    for threshold, title in config.RANKS:
        lines.append(f"{title} — от <b>{threshold}</b> сообщений")
    await message.reply("\n".join(lines), parse_mode="HTML")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.reply(
        "🤖 <b>Герда — хранительница чата</b>\n\n"
        "📌 <b>Команды:</b>\n"
        "/mystats — твоя статистика\n"
        "/top — топ-10 активных\n"
        "/mynick [прозвище] — задать себе прозвище\n"
        "/ranks — все ранги\n\n"
        "👮 <b>Для администраторов:</b>\n"
        "/setnick @user прозвище — дать прозвище\n"
        "/warn — предупреждение (ответом)\n"
        "/unwarn — снять предупреждения (ответом)\n"
        "/unmute — размутить пользователя (ответом)\n\n"
        "⚠️ <b>Правила чата:</b>\n"
        "• Без мата\n"
        "• Без спама\n"
        "• Без сторонних ссылок\n"
        f"• {config.WARN_LIMIT} предупреждения = мут + позорный титул на {SHAME_HOURS}ч 🎭",
        parse_mode="HTML"
    )


@dp.message(Command("roll"))
async def cmd_roll(message: Message):
    number = random.randint(1, 100)
    user = message.from_user
    name = display_name(user)
    if number >= 90:
        result = f"🎰 <b>{name}</b> бросает кубик... <b>{number}</b>! 🔥 ЛЕГЕНДАРНЫЙ БРОСОК!"
    elif number >= 70:
        result = f"🎰 <b>{name}</b> бросает кубик... <b>{number}</b>! 💪 Неплохо!"
    elif number >= 40:
        result = f"🎰 <b>{name}</b> бросает кубик... <b>{number}</b>. Средненько 😐"
    elif number >= 20:
        result = f"🎰 <b>{name}</b> бросает кубик... <b>{number}</b>. Ну такое 😬"
    else:
        result = f"🎰 <b>{name}</b> бросает кубик... <b>{number}</b>. 💀 Катастрофа!"
    await message.reply(result, parse_mode="HTML")


# ══ ОСНОВНОЙ ХЕНДЛЕР ══

@dp.message()
async def handle_message(message: Message):
    user = message.from_user
    if not user or user.is_bot:
        return

    if message.chat.type not in ("group", "supergroup"):
        return

    db.update_chat_activity()
    db.upsert_user(user.id, user.username or "", user.full_name or "")

    text = message.text or message.caption or ""

    if text and ("герда" in text.lower() or "@gerda_manager_bot" in text.lower()):
        await message.reply(random.choice(MENTION_REPLIES))
        return

    if text and contains_forbidden_link(text):
        try:
            await message.delete()
        except Exception:
            pass
        await warn_user(message, user, "не размещай чужие ссылки в чате! 🔗❌")
        return

    if text and contains_bad_word(text):
        await warn_user_bad(message, user)
        return

    if db.check_spam(user.id, config.SPAM_MAX_MESSAGES, config.SPAM_INTERVAL_SECONDS):
        name = display_name(user)
        await message.reply(
            f"🤐 <b>{name}</b>, не флуди! Мут на 1 минуту 📵",
            parse_mode="HTML"
        )
        await mute_user(message.chat.id, user.id, config.SPAM_MUTE_SECONDS)
        return

    old_row = db.get_user(user.id)
    old_msgs = old_row["messages"] if old_row else 0
    old_rank = db.get_rank(old_msgs)

    new_msgs = db.increment_messages(user.id)
    new_rank = db.get_rank(new_msgs)

    if new_rank != old_rank:
        name = display_name(user)
        await message.reply(
            f"🎊 <b>{name}</b> получил(а) новый ранг — <b>{new_rank}</b>! "
            f"Так держать, {new_msgs} сообщений — это сила! 💪",
            parse_mode="HTML"
        )


async def auto_message_scheduler():
    """Авто-сообщение когда чат молчит 4 часа."""
    global _last_auto_sent
    await asyncio.sleep(10)
    while True:
        await asyncio.sleep(60)
        try:
            last = db.get_last_activity()
            now = int(time.time())
            silent_for = now - last
            if silent_for >= config.AUTO_MESSAGE_INTERVAL:
                if now - _last_auto_sent >= config.AUTO_MESSAGE_INTERVAL:
                    msg = random.choice(AUTO_MESSAGES)
                    await bot.send_message(config.CHAT_ID, msg)
                    _last_auto_sent = now
                    logging.info(f"Авто-сообщение отправлено (тишина {silent_for}с)")
        except Exception as e:
            logging.error(f"Ошибка в планировщике: {e}")


async def auto_top_scheduler():
    """Авто-топ 3 каждые 6 часов."""
    await asyncio.sleep(30)
    while True:
        await asyncio.sleep(config.AUTO_TOP_INTERVAL)
        try:
            users = db.get_top_users(3)
            if not users:
                continue

            medals = ["🥇", "🥈", "🥉"]
            lines = ["🏆 <b>Топ-3 самых активных участников чата!</b>\n"]
            for i, row in enumerate(users):
                name = display_name_from_row(row)
                rank = db.get_rank(row["messages"])
                lines.append(f"{medals[i]} <b>{name}</b> — {row['messages']} сообщ. | {rank}")

            lines.append("\nПродолжайте в том же духе! 💪")
            await bot.send_message(config.CHAT_ID, "\n".join(lines), parse_mode="HTML")
            logging.info("Авто-топ 3 отправлен")
        except Exception as e:
            logging.error(f"Ошибка в авто-топ планировщике: {e}")


async def shame_expiry_scheduler():
    """Каждые 10 минут чистит истёкшие позорные прозвища."""
    while True:
        await asyncio.sleep(600)
        try:
            db.expire_shame_nicknames()
        except Exception as e:
            logging.error(f"Ошибка в планировщике прозвищ: {e}")


async def main():
    db.init_db()
    logging.info("Герда запускается... 🚀")
    asyncio.create_task(auto_message_scheduler())
    asyncio.create_task(auto_top_scheduler())
    asyncio.create_task(shame_expiry_scheduler())
    await dp.start_polling(bot, allowed_updates=["message", "chat_member"])


if __name__ == "__main__":
    asyncio.run(main())
