import web_server
import os, asyncio, logging, aiosqlite, re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

logging.basicConfig(level=logging.INFO)

API_ID = 31263273
API_HASH = "f61d7fcbb5ce902bca1ad838a70dab36"
BOT_TOKEN = "8646414364:AAG2Noctms_7vNKjEKqj97OyXXdF-X6brk8"
OWNER_ID = 7686703002

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
user_client = TelegramClient("premium_session", API_ID, API_HASH)

class DirectAddState(StatesGroup):
    media = State()
    code = State()
    title = State()

class MovieLinkState(StatesGroup):
    link = State()
    code = State()
    title = State()

class ClientAuthState(StatesGroup):
    phone, code, password = State(), State(), State()

class AdminChannelState(StatesGroup):
    add_channel, del_channel = State(), State()

class AdminBroadcastState(StatesGroup):
    message = State()

class AdminManageState(StatesGroup):
    add_admin, del_admin = State(), State()

async def init_db():
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                code TEXT PRIMARY KEY,
                title TEXT,
                file_id TEXT,
                file_type TEXT,
                channel_id INTEGER,
                message_id INTEGER,
                caption TEXT,
                views INTEGER DEFAULT 0
            )
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS bot_users (user_id INTEGER PRIMARY KEY)")
        await db.execute("CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, invite_link TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
        await db.commit()

async def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID: return True
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone() is not None

async def get_unsubscribed_channels(user_id: int):
    unsub = []
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT channel_id, invite_link FROM channels") as cur:
            channels = await cur.fetchall()
    for ch_id, link in channels:
        try:
            m = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if m.status not in ["member", "administrator", "creator"]:
                unsub.append((ch_id, link))
        except Exception:
            continue
    return unsub

def build_sub_kb(unsub_list):
    kb = []
    for i, (_, link) in enumerate(unsub_list, start=1):
        kb.append([InlineKeyboardButton(text=f"📢 {i}-Kanalga a'zo bo'lish", url=link)])
    kb.append([InlineKeyboardButton(text="✅ A'zo bo'ldim / Tekshirish", callback_data="check_all_subs")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_main_keyboard(is_adm=False):
    kb = [
        [KeyboardButton(text="🔥 Trenddagi kinolar"), KeyboardButton(text="🎲 Tasodifiy kino")],
        [KeyboardButton(text="📊 Bot statistikasi")]
    ]
    if is_adm:
        kb.append([KeyboardButton(text="⚙️ Admin Boshqaruv Paneli")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_panel_kb(is_owner=False):
    kb = [
        [InlineKeyboardButton(text="🎬 Oddiy yuklash (Fayl/Video)", callback_data="adm_add_direct"), InlineKeyboardButton(text="🔗 4 GB Havola orqali", callback_data="adm_add_kino_link")],
        [InlineKeyboardButton(text="🗑 Kino o'chirish", callback_data="adm_del_kino"), InlineKeyboardButton(text="🔐 Premium Akkaunt", callback_data="adm_auth_client")],
        [InlineKeyboardButton(text="📢 Majburiy kanallar", callback_data="adm_channels_menu")],
        [InlineKeyboardButton(text="📨 Xabar tarqatish", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📊 Hisobot", callback_data="adm_stats")]
    ]
    if is_owner:
        kb.append([InlineKeyboardButton(text="👥 Adminlarni boshqarish", callback_data="adm_manage_admins")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute("INSERT OR IGNORE INTO bot_users (user_id) VALUES (?)", (msg.from_user.id,))
        await db.commit()

    adm = await is_admin(msg.from_user.id)
    unsub = await get_unsubscribed_channels(msg.from_user.id)
    if unsub and not adm:
        return await msg.answer("⚠️ <b>Rasmiy kanallarimizga obuna bo'ling:</b>", reply_markup=build_sub_kb(unsub), parse_mode="HTML")

    parts = msg.text.split()
    if len(parts) > 1:
        return await search_and_send_movie(msg, parts[1].strip())

    await msg.answer(
        "👋 <b>Kinomanlar botiga xush kelibsiz!</b>\n\n"
        "🍿 Kino olish uchun uning <b>kodini</b> yoki <b>nomini</b> to'g'ridan-to'g'ri yozing (masalan: <code>2</code> yoki <code>Dakan</code>).",
        reply_markup=get_main_keyboard(adm),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "check_all_subs")
async def verify_subscription(cb: types.CallbackQuery):
    unsub = await get_unsubscribed_channels(cb.from_user.id)
    adm = await is_admin(cb.from_user.id)
    if not unsub:
        await cb.message.delete()
        await cb.message.answer("✅ <b>Obuna tasdiqlandi!</b>\nKino kodi yoki nomini yozishingiz mumkin:", reply_markup=get_main_keyboard(adm), parse_mode="HTML")
    else:
        await cb.answer("❌ Hali barcha kanallarga a'zo bo'lmadingiz!", show_alert=True)
# --- HAM KOD, HAM NOM BO'YICHA BIRLASHGAN QIDIRUV ---
async def search_and_send_movie(msg: types.Message, query: str):
    q = query.strip()
    q_lower = q.lower()

    async with aiosqlite.connect("kino_database.db") as db:
        # 1. Avval aniq kod yoki to'liq nom bo'yicha qidiramiz
        async with db.execute(
            "SELECT code, title, file_id, file_type, channel_id, message_id, caption, views FROM movies WHERE LOWER(code) = ? OR LOWER(title) = ?",
            (q_lower, q_lower)
        ) as cur:
            exact_match = await cur.fetchone()

        if exact_match:
            code, title, file_id, file_type, channel_id, message_id, caption, views = exact_match
            views += 1
            await db.execute("UPDATE movies SET views = ? WHERE code = ?", (views, code))
            await db.commit()

            cap = (
                f"🎬 <b>{title}</b>\n"
                f"🔢 Kodi: <code>{code}</code>\n"
                f"👁 Ko'rishlar: <b>{views}</b>\n\n"
                f"{caption}\n\n"
                f"🍿 @{bot._me.username} orqali yuklab olindi."
            )

            if channel_id and message_id:
                if not await user_client.is_user_authorized():
                    return await msg.answer("⚠️ Bot sozlanmoqda: Admin Premium akkauntni ulamagan.")
                wait_m = await msg.answer("⏳ <i>Kino yuklanmoqda...</i>", parse_mode="HTML")
                try:
                    await user_client.forward_messages(entity=msg.chat.id, messages=message_id, from_peer=channel_id)
                    await wait_m.delete()
                except Exception as e:
                    await wait_m.edit_text(f"❌ Xatolik: {e}")
                return

            if file_type == "photo":
                await msg.answer_photo(photo=file_id, caption=cap, parse_mode="HTML")
            elif file_type == "document":
                await msg.answer_document(document=file_id, caption=cap, parse_mode="HTML")
            else:
                await msg.answer_video(video=file_id, caption=cap, parse_mode="HTML")
            return

        # 2. Agar aniq chiqmasa, o'xshash nomlar bo'yicha qidiramiz
        async with db.execute("SELECT code, title FROM movies WHERE LOWER(title) LIKE ? LIMIT 6", (f"%{q_lower}%",)) as cur:
            partial_matches = await cur.fetchall()

    if partial_matches:
        txt = f"🔍 <b>'{q}' bo'yicha topilgan kinolar:</b>\n\n"
        for c, t in partial_matches:
            txt += f"• <b>{t}</b> — Kodi: <code>{c}</code>\n"
        txt += "\n<i>Kinoni yuklab olish uchun uning kodini yuboring!</i>"
        await msg.answer(txt, parse_mode="HTML")
    else:
        await msg.answer("❌ <b>Bunday kod yoki nomga ega kino topilmadi!</b>", parse_mode="HTML")

@dp.message(F.text == "⚙️ Admin Boshqaruv Paneli")
async def show_admin_panel(msg: types.Message):
    if not await is_admin(msg.from_user.id): return
    await msg.answer("👑 <b>Boshqaruv Paneli:</b>", reply_markup=get_admin_panel_kb(msg.from_user.id == OWNER_ID), parse_mode="HTML")

# --- KINO YUKLASH ---
@dp.callback_query(F.data == "adm_add_direct")
async def start_add_direct(cb: types.CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id): return
    await cb.message.answer("🎬 <b>Kinoning videosini yoki faylini yuboring:</b>", parse_mode="HTML")
    await state.set_state(DirectAddState.media)

@dp.message(DirectAddState.media, F.video | F.photo | F.document)
async def process_direct_media(msg: types.Message, state: FSMContext):
    if msg.video: f_id, f_type = msg.video.file_id, "video"
    elif msg.photo: f_id, f_type = msg.photo[-1].file_id, "photo"
    else: f_id, f_type = msg.document.file_id, "document"

    await state.update_data(f_id=f_id, f_type=f_type, caption=msg.caption or "")
    await msg.answer("✅ Fayl qabul qilindi!\n\n🔢 Ushbu kino uchun <b>kod</b> yuboring (masalan: <code>2</code>):", parse_mode="HTML")
    await state.set_state(DirectAddState.code)

@dp.message(DirectAddState.code)
async def process_direct_code(msg: types.Message, state: FSMContext):
    await state.update_data(code=msg.text.strip().lower())
    await msg.answer("📝 Kinoning <b>nomini</b> yozing (masalan: <i>Dakan</i>):", parse_mode="HTML")
    await state.set_state(DirectAddState.title)

@dp.message(DirectAddState.title)
async def process_direct_title(msg: types.Message, state: FSMContext):
    title = msg.text.strip()
    data = await state.get_data()
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO movies (code, title, file_id, file_type, caption) VALUES (?, ?, ?, ?, ?)",
            (data["code"], title, data["f_id"], data["f_type"], data["caption"])
        )
        await db.commit()
    await msg.answer(f"🎉 <b>Kino saqlandi!</b>\n\n🎬 Nom: <b>{title}</b>\n🔢 Kod: <code>{data['code']}</code>", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "adm_add_kino_link")
async def start_add_kino_link(cb: types.CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id): return
    await cb.message.answer("🔗 Post linkini yuboring (masalan: <code>https://t.me/c/2147483647/12</code>):", parse_mode="HTML")
    await state.set_state(MovieLinkState.link)

@dp.message(MovieLinkState.link)
async def process_movie_link(msg: types.Message, state: FSMContext):
    link = msg.text.strip()
    m_priv = re.search(r"t\.me/c/(\d+)/(\d+)", link)
    m_pub = re.search(r"t\.me/([^/]+)/(\d+)", link)
    if m_priv: ch_id, msg_id = int("-100" + m_priv.group(1)), int(m_priv.group(2))
    elif m_pub: ch_id, msg_id = m_pub.group(1), int(m_pub.group(2))
    else: return await msg.answer("❌ Havola noto'g'ri!")
    await state.update_data(channel_id=ch_id, message_id=msg_id)
    await msg.answer("🔢 Kod kiriting:", parse_mode="HTML")
    await state.set_state(MovieLinkState.code)

@dp.message(MovieLinkState.code)
async def process_link_code(msg: types.Message, state: FSMContext):
    await state.update_data(code=msg.text.strip().lower())
    await msg.answer("📝 Nomi:", parse_mode="HTML")
    await state.set_state(MovieLinkState.title)

@dp.message(MovieLinkState.title)
async def process_link_title(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO movies (code, title, channel_id, message_id, caption) VALUES (?, ?, ?, ?, ?)",
            (data["code"], msg.text.strip(), data["channel_id"], data["message_id"], "")
        )
        await db.commit()
    await msg.answer("🎉 <b>Kino saqlandi!</b>", parse_mode="HTML")
    await state.clear()

# --- PREMIUM AUTH ---
@dp.callback_query(F.data == "adm_auth_client")
async def start_auth_client(cb: types.CallbackQuery, state: FSMContext):
    if cb.from_user.id != OWNER_ID: return await cb.answer("Faqat Egaga!", show_alert=True)
    if await user_client.is_user_authorized(): return await cb.message.answer("✅ Premium akkaunt faol!")
    await cb.message.answer("📱 Raqam (+998...):")
    await state.set_state(ClientAuthState.phone)

@dp.message(ClientAuthState.phone)
async def process_auth_phone(msg: types.Message, state: FSMContext):
    phone = msg.text.strip()
    await user_client.connect()
    sent = await user_client.send_code_request(phone)
    await state.update_data(phone=phone, phone_code_hash=sent.phone_code_hash)
    await msg.answer("📩 Kodni yuboring:")
    await state.set_state(ClientAuthState.code)

@dp.message(ClientAuthState.code)
async def process_auth_code(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        await user_client.sign_in(data["phone"], msg.text.strip(), phone_code_hash=data["phone_code_hash"])
        await msg.answer("✅ Ulangan!")
        await state.clear()
    except SessionPasswordNeededError:
        await msg.answer("🔐 2FA Parol:")
        await state.set_state(ClientAuthState.password)

@dp.message(ClientAuthState.password)
async def process_auth_password(msg: types.Message, state: FSMContext):
    await user_client.sign_in(password=msg.text.strip())
    await msg.answer("✅ Tayyor!")
    await state.clear()

# --- ADMINLAR / KANALLAR ---
@dp.callback_query(F.data == "adm_manage_admins")
async def manage_admins_menu(cb: types.CallbackQuery):
    if cb.from_user.id != OWNER_ID: return
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT user_id FROM admins") as cur: alist = await cur.fetchall()
    text = "👥 <b>Adminlar:</b>\n\n" + "\n".join([f"• <code>{a[0]}</code>" for a in alist])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Qo'shish", callback_data="act_add_admin"), InlineKeyboardButton(text="➖ O'chirish", callback_data="act_del_admin")],
        [InlineKeyboardButton(text="⬅️ Panel", callback_data="back_adm_menu")]
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "act_add_admin")
async def ask_new_admin_id(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("ID yuboring:")
    await state.set_state(AdminManageState.add_admin)

@dp.message(AdminManageState.add_admin)
async def process_new_admin(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Raqam yozing:")
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(msg.text),))
        await db.commit()
    await msg.answer("✅ Qo'shildi!")
    await state.clear()

@dp.callback_query(F.data == "act_del_admin")
async def ask_del_admin_id(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("ID yuboring:")
    await state.set_state(AdminManageState.del_admin)

@dp.message(AdminManageState.del_admin)
async def process_del_admin(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("Raqam yozing:")
    uid = int(msg.text)
    if uid == OWNER_ID: return await msg.answer("O'zingizni o'chira olmaysiz!")
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute("DELETE FROM admins WHERE user_id = ?", (uid,))
        await db.commit()
    await msg.answer("✅ O'chirildi!")
    await state.clear()

@dp.callback_query(F.data == "adm_del_kino")
async def delete_kino_req(cb: types.CallbackQuery):
    await cb.message.answer("Format: <code>/del 101</code>", parse_mode="HTML")

@dp.message(Command("del"))
async def execute_del(msg: types.Message):
    if not await is_admin(msg.from_user.id): return
    p = msg.text.split()
    if len(p) < 2: return await msg.answer("Kodni yozing!")
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute("DELETE FROM movies WHERE code = ?", (p[1].lower(),))
        await db.commit()
    await msg.answer("✅ O'chirildi!")

@dp.callback_query(F.data == "adm_channels_menu")
async def channels_setting(cb: types.CallbackQuery):
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT channel_id, invite_link FROM channels") as cur: chs = await cur.fetchall()
    text = "📢 <b>Kanallar:</b>\n\n" + ("\n".join([f"• <code>{c[0]}</code>" for c in chs]) if chs else "Bo'sh")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Ulash", callback_data="add_ch_act"), InlineKeyboardButton(text="➖ O'chirish", callback_data="del_ch_act")],
        [InlineKeyboardButton(text="⬅️ Panel", callback_data="back_adm_menu")]
    ])
    await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "add_ch_act")
async def req_add_channel(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("Format: <code>@kanal https://t.me/kanal</code>", parse_mode="HTML")
    await state.set_state(AdminChannelState.add_channel)

@dp.message(AdminChannelState.add_channel)
async def process_channel_pair(msg: types.Message, state: FSMContext):
    p = msg.text.split()
    if len(p) < 2: return await msg.answer("Probel bilan yozing!")
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute("INSERT OR REPLACE INTO channels VALUES (?, ?)", (p[0], p[1]))
        await db.commit()
    await msg.answer("✅ Ulandi!")
    await state.clear()

@dp.callback_query(F.data == "del_ch_act")
async def req_del_channel(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("Kanal username:")
    await state.set_state(AdminChannelState.del_channel)

@dp.message(AdminChannelState.del_channel)
async def process_del_channel(msg: types.Message, state: FSMContext):
    async with aiosqlite.connect("kino_database.db") as db:
        await db.execute("DELETE FROM channels WHERE channel_id = ?", (msg.text.strip(),))
        await db.commit()
    await msg.answer("✅ O'chirildi!")
    await state.clear()

@dp.callback_query(F.data == "adm_stats")
async def adm_detailed_stats(cb: types.CallbackQuery):
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT COUNT(*) FROM bot_users") as cur: u_cnt = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*), SUM(views) FROM movies") as cur:
            m_data = await cur.fetchone()
    await cb.message.answer(f"👥 Userlar: <b>{u_cnt}</b> | 🎬 Kinolar: <b>{m_data[0]}</b> | 👁 Ko'rishlar: <b>{m_data[1] or 0}</b>", parse_mode="HTML")

@dp.callback_query(F.data == "adm_broadcast")
async def broad_req(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("Xabarni yuboring (/cancel):")
    await state.set_state(AdminBroadcastState.message)

@dp.message(AdminBroadcastState.message)
async def broad_exec(msg: types.Message, state: FSMContext):
    if msg.text == "/cancel":
        await state.clear()
        return await msg.answer("Bekor qilindi.")
    s_msg = await msg.answer("Yuborilmoqda...")
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT user_id FROM bot_users") as cur: users = await cur.fetchall()
    s = 0
    for u in users:
        try:
            await msg.copy_to(chat_id=u[0])
            s += 1
            await asyncio.sleep(0.05)
        except Exception: pass
    await s_msg.edit_text(f"✅ <b>{s}</b> ta foydalanuvchiga yuborildi!", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "back_adm_menu")
async def back_menu(cb: types.CallbackQuery):
    await cb.message.edit_text("👑 <b>Boshqaruv Paneli:</b>", reply_markup=get_admin_panel_kb(cb.from_user.id == OWNER_ID), parse_mode="HTML")

@dp.message(F.text == "🔥 Trenddagi kinolar")
async def show_trending(msg: types.Message):
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT code, title, views FROM movies ORDER BY views DESC LIMIT 5") as cur: top = await cur.fetchall()
    if not top: return await msg.answer("📭 Hozircha kinolar yo'q.")
    t = "🔥 <b>TOP-5 Kinolar:</b>\n\n" + "\n".join([f"{i}. <b>{x[1]}</b> (Kod: <code>{x[0]}</code>, 👁 {x[2]})" for i, x in enumerate(top, 1)])
    await msg.answer(t, parse_mode="HTML")

@dp.message(F.text == "🎲 Tasodifiy kino")
async def show_random(msg: types.Message):
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT code FROM movies ORDER BY RANDOM() LIMIT 1") as cur: r = await cur.fetchone()
    if r: await search_and_send_movie(msg, r[0])
    else: await msg.answer("📭 Bazada kino yo'q.")

@dp.message(F.text == "📊 Bot statistikasi")
async def user_stat_view(msg: types.Message):
    async with aiosqlite.connect("kino_database.db") as db:
        async with db.execute("SELECT COUNT(*) FROM bot_users") as cur: u = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM movies") as cur: m = (await cur.fetchone())[0]
    await msg.answer(f"📊 Foydalanuvchilar: <b>{u}</b> | Kinolar: <b>{m}</b>", parse_mode="HTML")

# --- FOYDALANUVCHI YOZGAN HAR QANDAY MATN TO'G'RIDAN-TO'G'RI QIDIRILADI ---
@dp.message(F.text)
async def direct_search_handler(msg: types.Message):
    adm = await is_admin(msg.from_user.id)
    unsub = await get_unsubscribed_channels(msg.from_user.id)
    if unsub and not adm:
        return await msg.answer("⚠️ <b>Avval kanallarga a'zo bo'ling:</b>", reply_markup=build_sub_kb(unsub), parse_mode="HTML")
    await search_and_send_movie(msg, msg.text.strip())

async def main():
    await init_db()
    bot._me = await bot.get_me()
    await user_client.connect()
    logging.info("Kino Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
