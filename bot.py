import os
import logging
import sqlite3
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)

# ─── الإعدادات ───────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8988952636:AAF_FU7oOib8JF_O1fACXp16-k9KPLJtXb4")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBNssTWMrbHMQZDXrvMPNF4HJ2m_SnI5CY")
OWNER_ID       = int(os.getenv("OWNER_ID", "0"))   # ضع ID تيليجرام الخاص بك هنا

CHANNEL_USERNAME = "@AmousTechnology"
GROUP_USERNAME   = "@IAmousTechnologychat"

TELEBIRR_NUMBER  = "251975969602"
TON_WALLET       = "UQAxa3Mj-RIcVz5V6jILtv3Xc0Oo4pVSBJJePMtCJ-OfBxJ8"
BINANCE_UID      = "1188480616"

FREE_MSG_LIMIT   = 50
FREE_IMG_LIMIT   = 10

PLANS = {
    "1month":  {"label": "شهر واحد / 1 Month",   "days": 30,  "usd": 2,  "etb": 110},
    "3months": {"label": "3 أشهر / 3 Months",     "days": 90,  "usd": 5,  "etb": 275},
    "6months": {"label": "6 أشهر / 6 Months",     "days": 180, "usd": 8,  "etb": 440},
    "1year":   {"label": "سنة كاملة / 1 Year",    "days": 365, "usd": 12, "etb": 660},
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── قاعدة البيانات ──────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id       INTEGER PRIMARY KEY,
        username      TEXT,
        full_name     TEXT,
        language      TEXT    DEFAULT 'ar',
        msg_count     INTEGER DEFAULT 0,
        img_count     INTEGER DEFAULT 0,
        last_reset    TEXT,
        is_premium    INTEGER DEFAULT 0,
        premium_expiry TEXT,
        joined_at     TEXT,
        is_banned     INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER,
        plan       TEXT,
        method     TEXT,
        status     TEXT DEFAULT 'pending',
        created_at TEXT
    )""")
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def create_user(user_id, username, full_name, language="ar"):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""INSERT OR IGNORE INTO users
        (user_id,username,full_name,language,msg_count,img_count,last_reset,joined_at)
        VALUES (?,?,?,?,0,0,?,?)""",
        (user_id, username, full_name, language, now, now))
    conn.commit()
    conn.close()

def update_user(user_id, **kw):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    for k, v in kw.items():
        c.execute(f"UPDATE users SET {k}=? WHERE user_id=?", (v, user_id))
    conn.commit()
    conn.close()

def reset_if_needed(user_id):
    row = get_user(user_id)
    if not row: return
    last = datetime.fromisoformat(row[6]) if row[6] else datetime.now()
    if datetime.now() - last >= timedelta(hours=24):
        update_user(user_id, msg_count=0, img_count=0,
                    last_reset=datetime.now().isoformat())
        return True   # تجدّد
    return False

def user_is_premium(user_id):
    row = get_user(user_id)
    if not row or not row[8]: return False
    return datetime.fromisoformat(row[8]) > datetime.now()

def activate_premium(user_id, days):
    expiry = datetime.now() + timedelta(days=days)
    update_user(user_id, is_premium=1, premium_expiry=expiry.isoformat())

# ─── النصوص المتعددة اللغات ─────────────────────────────────────
T = {
"ar": {
"welcome"          : "👋 مرحباً! أنا *أمير*، مساعدك الذكي! 🤖\nاختر لغتك أولاً:",
"sub_required"     : "⚠️ يا {name}!\nللاستخدام يجب الاشتراك في:\n📢 القناة: {ch}\n👥 الجروب: {gr}\n\nبعد الاشتراك اضغط ✅ تحقق",
"sub_welcome"      : "🎉 أهلاً وسهلاً يا *{name}*!\nأنا أمير مساعدك الذكي 🌟\n\nأقدر أساعدك في:\n📖 تفسير القرآن والأحاديث\n🍳 وصفات طبخ\n😂 نكت ومزاح\n💼 كتابة CV\n🖼 توليد صور\n❓ أي سؤال تريده!\n\nلديك *{msgs}* رسالة و*{imgs}* صورة مجانية يومياً 🎁",
"left"             : "يا {name} 👋\nلاحظت أنك غادرت القناة أو الجروب 😊\nعد إلينا واشترك مجدداً لنكمل حديثنا!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "يا {name} 🌟 أحسنت اليوم!\nاستخدمت {lim} رسالة.\nرسائلك تتجدد غداً في نفس الوقت ⏰\n\nأو اشترك في البريميوم الآن! 💎",
"limit_img"        : "يا {name} 🌟 استخدمت {lim} صورة اليوم!\nصورك تتجدد غداً ⏰\n\nأو اشترك في البريميوم! 💎",
"reset_notif"      : "🎉 يا {name}!\nيومك تجدد! يمكنك الآن إرسال الرسائل والصور من جديد 🚀",
"prem_activated"   : "🎊 مبروك يا {name}!\nتم تفعيل اشتراكك *{plan}* المميز 👑\n\n✅ رسائل غير محدودة\n✅ صور غير محدودة\n✅ جودة أعلى وردود أذكى\n\nشكراً لثقتك بنا! 🤩",
"prem_expiring"    : "⏰ يا {name}!\nاشتراكك المميز سينتهي بعد 3 أيام!\nجدد الآن واستمر في الاستمتاع 🚀",
"prem_expired"     : "يا {name} 😊\nانتهى اشتراكك المميز اليوم.\nشكراً لثقتك بنا!\nاشترك مجدداً للاستمرار 💎",
"check_btn"        : "✅ تحقق من الاشتراك",
"prem_btn"         : "💎 اشترك في البريميوم",
"lang_changed"     : "✅ تم تغيير اللغة إلى العربية!",
},
"en": {
"welcome"          : "👋 Hello! I'm *Amir*, your smart assistant! 🤖\nChoose your language first:",
"sub_required"     : "⚠️ Hey {name}!\nPlease subscribe first:\n📢 Channel: {ch}\n👥 Group: {gr}\n\nAfter subscribing press ✅ Verify",
"sub_welcome"      : "🎉 Welcome *{name}*!\nI'm Amir, your smart assistant 🌟\n\nI can help you with:\n📖 Quran & Hadith\n🍳 Recipes\n😂 Jokes\n💼 CV Writing\n🖼 Image Generation\n❓ Any question!\n\nYou have *{msgs}* messages & *{imgs}* images free daily 🎁",
"left"             : "Hey {name} 👋\nI noticed you left our channel or group 😊\nRejoin to continue chatting!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "Hey {name} 🌟 Great job today!\nYou used {lim} messages.\nYour messages reset in 24 hours ⏰\n\nOr subscribe to Premium now! 💎",
"limit_img"        : "Hey {name} 🌟 You used {lim} images today!\nImages reset in 24 hours ⏰\n\nOr subscribe to Premium! 💎",
"reset_notif"      : "🎉 Hey {name}!\nYour daily limit has reset! You can send messages and images again 🚀",
"prem_activated"   : "🎊 Congratulations {name}!\nYour *{plan}* Premium subscription is now active 👑\n\n✅ Unlimited messages\n✅ Unlimited images\n✅ Higher quality\n\nThank you for your trust! 🤩",
"prem_expiring"    : "⏰ Hey {name}!\nYour Premium expires in 3 days!\nRenew now to keep enjoying 🚀",
"prem_expired"     : "Hey {name} 😊\nYour Premium ended today.\nSubscribe again to continue 💎",
"check_btn"        : "✅ Verify Subscription",
"prem_btn"         : "💎 Subscribe to Premium",
"lang_changed"     : "✅ Language changed to English!",
},
"am": {
"welcome"          : "👋 ሰላም! እኔ *አሚር* ነኝ፣ ብልህ ረዳትህ! 🤖\nቋንቋህን ምረጥ:",
"sub_required"     : "⚠️ {name}!\nመጀመሪያ ተቀላቀል:\n📢 ቻናል: {ch}\n👥 ቡድን: {gr}\n\nተቀላቀለ ✅ ተጫን",
"sub_welcome"      : "🎉 እንኳን ደህና መጣህ *{name}*!\nእኔ አሚር ነኝ 🌟\nቀን {msgs} መልዕክቶች እና {imgs} ምስሎች ነፃ ናቸው 🎁",
"left"             : "{name} 👋\nቻናሉን ወይም ቡድኑን ለቀህ ወጣህ 😊\nለመቀጠል እንደገና ተቀላቀል!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "{name} 🌟 ዛሬ {lim} መልዕክቶች ተጠቀምህ!\nነገ ይታደሳሉ ⏰\nወይም ፕሪሚየም ተቀላቀል! 💎",
"limit_img"        : "{name} 🌟 ዛሬ {lim} ምስሎች ተጠቀምህ!\nነገ ይታደሳሉ ⏰",
"reset_notif"      : "🎉 {name}!\nቀኑ ታደሰ! እንደገና ልትጠቀም ትችላለህ 🚀",
"prem_activated"   : "🎊 እንኳን ደስ አለህ {name}!\n*{plan}* ፕሪሚየም ነቅቷል 👑\n✅ ያልተወሰነ ✅ ያልተወሰነ ምስሎች",
"prem_expiring"    : "⏰ {name}! ፕሪሚየምህ በ3 ቀናት ያልቃል! አሁን አድስ 🚀",
"prem_expired"     : "{name} 😊 ፕሪሚየምህ ዛሬ አለቀ. እንደገና ተቀላቀል 💎",
"check_btn"        : "✅ ማረጋገጫ",
"prem_btn"         : "💎 ፕሪሚየም ተቀላቀል",
"lang_changed"     : "✅ ቋንቋ ወደ አማርኛ ተቀየረ!",
},
"fr": {
"welcome"          : "👋 Bonjour! Je suis *Amir*, votre assistant intelligent! 🤖\nChoisissez votre langue:",
"sub_required"     : "⚠️ {name}!\nAbonnez-vous d'abord:\n📢 Canal: {ch}\n👥 Groupe: {gr}\n\nEnsuite appuyez ✅ Vérifier",
"sub_welcome"      : "🎉 Bienvenue *{name}*!\nJe suis Amir 🌟\n{msgs} messages & {imgs} images gratuits par jour 🎁",
"left"             : "{name} 👋\nVous avez quitté le canal ou le groupe 😊\nRejoignez-nous!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "{name} 🌟 Vous avez utilisé {lim} messages!\nRenouvellement demain ⏰\nOu abonnez-vous au Premium! 💎",
"limit_img"        : "{name} 🌟 Vous avez utilisé {lim} images!\nRenouvellement demain ⏰",
"reset_notif"      : "🎉 {name}! Votre limite a été réinitialisée 🚀",
"prem_activated"   : "🎊 Félicitations {name}!\n*{plan}* Premium actif 👑",
"prem_expiring"    : "⏰ {name}! Premium expire dans 3 jours! Renouvelez maintenant 🚀",
"prem_expired"     : "{name} 😊 Premium terminé. Abonnez-vous à nouveau 💎",
"check_btn"        : "✅ Vérifier",
"prem_btn"         : "💎 S'abonner",
"lang_changed"     : "✅ Langue changée en Français!",
},
"tr": {
"welcome"          : "👋 Merhaba! Ben *Amir*, akıllı asistanınız! 🤖\nDilinizi seçin:",
"sub_required"     : "⚠️ {name}!\nLütfen önce abone olun:\n📢 Kanal: {ch}\n👥 Grup: {gr}\n\nAbone olduktan sonra ✅ Doğrula",
"sub_welcome"      : "🎉 Hoş geldiniz *{name}*!\nBen Amir 🌟\nGünlük {msgs} mesaj & {imgs} resim ücretsiz 🎁",
"left"             : "{name} 👋\nKanalı veya grubu terk ettiniz 😊\nDevam için yeniden katılın!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "{name} 🌟 Bugün {lim} mesaj kullandınız!\nYarın yenilenecek ⏰\nPremium'a abone olun! 💎",
"limit_img"        : "{name} 🌟 Bugün {lim} resim kullandınız!\nYarın yenilenecek ⏰",
"reset_notif"      : "🎉 {name}! Günlük limitiniz yenilendi 🚀",
"prem_activated"   : "🎊 Tebrikler {name}!\n*{plan}* Premium aktif 👑",
"prem_expiring"    : "⏰ {name}! Premium 3 günde sona eriyor! Şimdi yenileyin 🚀",
"prem_expired"     : "{name} 😊 Premium sona erdi. Tekrar abone olun 💎",
"check_btn"        : "✅ Doğrula",
"prem_btn"         : "💎 Premium Abone",
"lang_changed"     : "✅ Dil Türkçe olarak değiştirildi!",
},
"ru": {
"welcome"          : "👋 Привет! Я *Амир*, ваш умный помощник! 🤖\nВыберите язык:",
"sub_required"     : "⚠️ {name}!\nСначала подпишитесь:\n📢 Канал: {ch}\n👥 Группа: {gr}\n\nПосле подписки нажмите ✅",
"sub_welcome"      : "🎉 Добро пожаловать *{name}*!\nЯ Амир 🌟\n{msgs} сообщений & {imgs} изображений бесплатно в день 🎁",
"left"             : "{name} 👋\nВы покинули канал или группу 😊\nПожалуйста, снова подпишитесь!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "{name} 🌟 Вы использовали {lim} сообщений!\nОбновится завтра ⏰\nПодпишитесь на Premium! 💎",
"limit_img"        : "{name} 🌟 Вы использовали {lim} изображений!\nОбновится завтра ⏰",
"reset_notif"      : "🎉 {name}! Ваш дневной лимит обновлён 🚀",
"prem_activated"   : "🎊 Поздравляем {name}!\n*{plan}* Premium активен 👑",
"prem_expiring"    : "⏰ {name}! Premium истекает через 3 дня! Продлите сейчас 🚀",
"prem_expired"     : "{name} 😊 Premium истёк. Подпишитесь снова 💎",
"check_btn"        : "✅ Проверить",
"prem_btn"         : "💎 Premium",
"lang_changed"     : "✅ Язык изменён на Русский!",
},
"id": {
"welcome"          : "👋 Halo! Saya *Amir*, asisten cerdas Anda! 🤖\nPilih bahasa Anda:",
"sub_required"     : "⚠️ {name}!\nSilakan bergabung dulu:\n📢 Saluran: {ch}\n👥 Grup: {gr}\n\nSetelah bergabung tekan ✅",
"sub_welcome"      : "🎉 Selamat datang *{name}*!\nSaya Amir 🌟\n{msgs} pesan & {imgs} gambar gratis per hari 🎁",
"left"             : "{name} 👋\nAnda meninggalkan saluran atau grup 😊\nGabung kembali!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "{name} 🌟 Anda menggunakan {lim} pesan hari ini!\nDiperbarui besok ⏰\nBerlangganan Premium! 💎",
"limit_img"        : "{name} 🌟 Anda menggunakan {lim} gambar hari ini!\nDiperbarui besok ⏰",
"reset_notif"      : "🎉 {name}! Batas harian Anda diperbarui 🚀",
"prem_activated"   : "🎊 Selamat {name}!\n*{plan}* Premium aktif 👑",
"prem_expiring"    : "⏰ {name}! Premium berakhir dalam 3 hari! Perbarui sekarang 🚀",
"prem_expired"     : "{name} 😊 Premium berakhir. Berlangganan lagi 💎",
"check_btn"        : "✅ Verifikasi",
"prem_btn"         : "💎 Premium",
"lang_changed"     : "✅ Bahasa diubah ke Indonesia!",
},
"fa": {
"welcome"          : "👋 سلام! من *امیر*، دستیار هوشمند شما هستم! 🤖\nزبان خود را انتخاب کنید:",
"sub_required"     : "⚠️ {name}!\nلطفاً ابتدا عضو شوید:\n📢 کانال: {ch}\n👥 گروه: {gr}\n\nپس از عضویت ✅ تأیید را بزنید",
"sub_welcome"      : "🎉 خوش آمدید *{name}*!\nمن امیر هستم 🌟\nروزانه {msgs} پیام و {imgs} تصویر رایگان 🎁",
"left"             : "{name} 👋\nکانال یا گروه را ترک کردید 😊\nبرای ادامه دوباره عضو شوید!\n📢 {ch}\n👥 {gr}",
"limit_msg"        : "{name} 🌟 امروز {lim} پیام استفاده کردید!\nفردا تجدید می‌شود ⏰\nدر پریمیوم عضو شوید! 💎",
"limit_img"        : "{name} 🌟 امروز {lim} تصویر استفاده کردید!\nفردا تجدید می‌شود ⏰",
"reset_notif"      : "🎉 {name}! حد روزانه شما تجدید شد 🚀",
"prem_activated"   : "🎊 تبریک {name}!\n*{plan}* پریمیوم فعال شد 👑",
"prem_expiring"    : "⏰ {name}! پریمیوم شما در 3 روز تمام می‌شود! همین الان تجدید کنید 🚀",
"prem_expired"     : "{name} 😊 پریمیوم شما تمام شد. دوباره عضو شوید 💎",
"check_btn"        : "✅ تأیید",
"prem_btn"         : "💎 پریمیوم",
"lang_changed"     : "✅ زبان به فارسی تغییر کرد!",
},
}

def tx(lang, key, **kw):
    lang = lang if lang in T else "ar"
    text = T[lang].get(key, T["ar"].get(key, ""))
    return text.format(**kw)

# ─── لوحة المفاتيح ───────────────────────────────────────────────
def kb_lang():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية",  callback_data="lang_ar"),
         InlineKeyboardButton("🇬🇧 English",   callback_data="lang_en")],
        [InlineKeyboardButton("🇪🇹 አማርኛ",    callback_data="lang_am"),
         InlineKeyboardButton("🇫🇷 Français",  callback_data="lang_fr")],
        [InlineKeyboardButton("🇹🇷 Türkçe",   callback_data="lang_tr"),
         InlineKeyboardButton("🇷🇺 Русский",   callback_data="lang_ru")],
        [InlineKeyboardButton("🇮🇩 Indonesia", callback_data="lang_id"),
         InlineKeyboardButton("🇮🇷 فارسی",    callback_data="lang_fa")],
    ])

def kb_sub(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 القناة / Channel", url="https://t.me/AmousTechnology")],
        [InlineKeyboardButton("👥 الجروب / Group",   url="https://t.me/IAmousTechnologychat")],
        [InlineKeyboardButton(tx(lang,"check_btn"),  callback_data="check_sub")],
    ])

def kb_premium():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🥉 شهر / 1 Month  — 2$ / 110 ETB",  callback_data="buy_1month")],
        [InlineKeyboardButton("🥈 3 أشهر / 3M   — 5$ / 275 ETB",  callback_data="buy_3months")],
        [InlineKeyboardButton("🥇 6 أشهر / 6M   — 8$ / 440 ETB",  callback_data="buy_6months")],
        [InlineKeyboardButton("👑 سنة / 1 Year  — 12$ / 660 ETB", callback_data="buy_1year")],
    ])

def kb_payment(plan_key):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 TeleBirr",    callback_data=f"pay_telebirr_{plan_key}")],
        [InlineKeyboardButton("💎 TON Wallet",  callback_data=f"pay_ton_{plan_key}")],
        [InlineKeyboardButton("🔶 Binance Pay", callback_data=f"pay_binance_{plan_key}")],
    ])

def kb_paid(plan_key):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ أرسلت الدفع / I Paid", callback_data=f"sent_{plan_key}")],
    ])

def kb_prem_prompt(lang):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tx(lang,"prem_btn"), callback_data="show_premium")],
    ])

# ─── Gemini ──────────────────────────────────────────────────────
def ask_gemini(prompt, name):
    url = (f"https://generativelanguage.googleapis.com/v1beta/"
           f"models/gemini-pro:generateContent?key={GEMINI_API_KEY}")
    sys_msg = (f"أنت أمير، مساعد ذكي ودود وخبير. تتحدث مع {name}. "
               f"أجب تلقائياً بلغة المستخدم. كن مفيداً، ودوداً، ومميزاً.")
    body = {"contents":[{"parts":[{"text":f"{sys_msg}\n\nالمستخدم: {prompt}"}]}]}
    try:
        r = requests.post(url, json=body, timeout=30)
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return "عذراً، حدث خطأ مؤقت. حاول مرة أخرى 😊"

def image_url(prompt):
    p = requests.utils.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{p}?width=512&height=512&nologo=true"

# ─── التحقق من الاشتراك ──────────────────────────────────────────
async def is_subscribed(bot, uid):
    try:
        ch = await bot.get_chat_member(CHANNEL_USERNAME, uid)
        gr = await bot.get_chat_member(GROUP_USERNAME,   uid)
        ok_ch = ch.status not in [ChatMember.LEFT, ChatMember.BANNED]
        ok_gr = gr.status not in [ChatMember.LEFT, ChatMember.BANNED]
        return ok_ch and ok_gr
    except:
        return False

# ─── الأوامر ─────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not get_user(u.id):
        create_user(u.id, u.username or "", u.full_name)
    await update.message.reply_text(
        "👋 Welcome / مرحباً / እንኳን ደህና መጡ!\n\n🌍 Choose language / اختر لغتك:",
        reply_markup=kb_lang()
    )

async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌍 Choose your language:", reply_markup=kb_lang())

async def cmd_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💎 اختر خطة الاشتراك / Choose a plan:\n\n"
        "🥉 شهر / 1 Month  → 2$ / 110 ETB\n"
        "🥈 3 أشهر / 3M   → 5$ / 275 ETB\n"
        "🥇 6 أشهر / 6M   → 8$ / 440 ETB\n"
        "👑 سنة / 1 Year  → 12$ / 660 ETB",
        reply_markup=kb_premium()
    )

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    total   = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    premium = c.execute("SELECT COUNT(*) FROM users WHERE is_premium=1").fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM payments WHERE status='pending'").fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"📊 إحصائيات البوت:\n\n"
        f"👥 إجمالي المستخدمين: {total}\n"
        f"💎 مشتركون مدفوعون: {premium}\n"
        f"⏳ طلبات دفع معلقة: {pending}"
    )

async def cmd_givepremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        tid  = int(ctx.args[0])
        days = int(ctx.args[1]) if len(ctx.args) > 1 else 30
        activate_premium(tid, days)
        row  = get_user(tid)
        lang = row[3] if row else "ar"
        name = row[2] if row else "المستخدم"
        plan_label = f"{days} يوم / {days} days"
        await ctx.bot.send_message(tid, tx(lang,"prem_activated", name=name, plan=plan_label), parse_mode="Markdown")
        await update.message.reply_text(f"✅ تم تفعيل البريميوم للمستخدم {tid} لمدة {days} يوم!")
    except Exception as e:
        await update.message.reply_text(f"الاستخدام: /givepremium [user_id] [days]\nخطأ: {e}")

async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        tid = int(ctx.args[0])
        update_user(tid, is_banned=1)
        await update.message.reply_text(f"✅ تم حظر المستخدم {tid}")
    except:
        await update.message.reply_text("الاستخدام: /ban [user_id]")

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args:
        await update.message.reply_text("الاستخدام: /broadcast [الرسالة]")
        return
    msg  = " ".join(ctx.args)
    conn = sqlite3.connect("bot.db")
    rows = conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()
    conn.close()
    sent = 0
    for (uid,) in rows:
        try:
            await ctx.bot.send_message(uid, msg)
            sent += 1
        except: pass
    await update.message.reply_text(f"✅ أُرسلت لـ {sent} مستخدم!")

# ─── رسائل النص ──────────────────────────────────────────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u    = update.effective_user
    text = update.message.text or ""
    row  = get_user(u.id)

    if not row:
        create_user(u.id, u.username or "", u.full_name)
        row = get_user(u.id)

    if row[10]: return          # محظور

    lang = row[3]
    name = u.first_name or u.username or "صديقي"

    # تحقق اشتراك
    if not await is_subscribed(ctx.bot, u.id):
        await update.message.reply_text(
            tx(lang,"sub_required", name=name, ch=CHANNEL_USERNAME, gr=GROUP_USERNAME),
            reply_markup=kb_sub(lang)
        )
        return

    # تجديد يومي مع إشعار
    was_reset = reset_if_needed(u.id)
    row = get_user(u.id)
    if was_reset:
        await update.message.reply_text(tx(lang,"reset_notif", name=name))

    # كشف طلب صورة
    img_keywords = ["صورة","صوره","ارسم","generate image","image of","draw","/image"]
    is_img = any(kw in text.lower() for kw in img_keywords)

    if is_img:
        if not user_is_premium(u.id) and row[5] >= FREE_IMG_LIMIT:
            await update.message.reply_text(
                tx(lang,"limit_img", name=name, lim=FREE_IMG_LIMIT),
                reply_markup=kb_prem_prompt(lang)
            )
            return
        prompt = text
        for kw in img_keywords: prompt = prompt.replace(kw,"")
        prompt = prompt.strip() or "beautiful landscape"
        wait = await update.message.reply_text("🎨 أمير يرسم لك...")
        url  = image_url(prompt)
        update_user(u.id, img_count=row[5]+1)
        await wait.delete()
        await update.message.reply_photo(url, caption=f"🎨 صورتك يا {name}!")
        return

    # حد الرسائل
    if not user_is_premium(u.id) and row[4] >= FREE_MSG_LIMIT:
        await update.message.reply_text(
            tx(lang,"limit_msg", name=name, lim=FREE_MSG_LIMIT),
            reply_markup=kb_prem_prompt(lang)
        )
        return

    wait = await update.message.reply_text("⏳ أمير يفكر...")
    reply = ask_gemini(text, name)
    update_user(u.id, msg_count=row[4]+1)
    await wait.delete()
    await update.message.reply_text(reply, parse_mode="Markdown")

# ─── الأزرار ─────────────────────────────────────────────────────
async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    u    = q.from_user
    data = q.data
    await q.answer()

    row  = get_user(u.id)
    lang = row[3] if row else "ar"
    name = u.first_name or u.username or "صديقي"

    # ── اختيار لغة ──
    if data.startswith("lang_"):
        chosen = data[5:]
        if not row:
            create_user(u.id, u.username or "", u.full_name, chosen)
        else:
            update_user(u.id, language=chosen)
        lang = chosen

        if not await is_subscribed(ctx.bot, u.id):
            await q.edit_message_text(
                tx(lang,"sub_required", name=name, ch=CHANNEL_USERNAME, gr=GROUP_USERNAME),
                reply_markup=kb_sub(lang)
            )
        else:
            await q.edit_message_text(
                tx(lang,"sub_welcome", name=name, msgs=FREE_MSG_LIMIT, imgs=FREE_IMG_LIMIT),
                parse_mode="Markdown"
            )
        return

    # ── تحقق اشتراك ──
    if data == "check_sub":
        if await is_subscribed(ctx.bot, u.id):
            await q.edit_message_text(
                tx(lang,"sub_welcome", name=name, msgs=FREE_MSG_LIMIT, imgs=FREE_IMG_LIMIT),
                parse_mode="Markdown"
            )
        else:
            await q.edit_message_text(
                tx(lang,"sub_required", name=name, ch=CHANNEL_USERNAME, gr=GROUP_USERNAME),
                reply_markup=kb_sub(lang)
            )
        return

    # ── عرض البريميوم ──
    if data == "show_premium":
        await q.edit_message_text(
            "💎 اختر خطة / Choose plan:\n\n"
            "🥉 شهر / 1M  → 2$ / 110 ETB\n"
            "🥈 3 أشهر / 3M → 5$ / 275 ETB\n"
            "🥇 6 أشهر / 6M → 8$ / 440 ETB\n"
            "👑 سنة / 1Y → 12$ / 660 ETB",
            reply_markup=kb_premium()
        )
        return

    # ── اختيار خطة ──
    if data.startswith("buy_"):
        pk   = data[4:]
        plan = PLANS.get(pk)
        if plan:
            await q.edit_message_text(
                f"✅ اخترت: *{plan['label']}*\n💵 {plan['usd']}$ / {plan['etb']} ETB\n\nاختر طريقة الدفع:",
                reply_markup=kb_payment(pk),
                parse_mode="Markdown"
            )
        return

    # ── TeleBirr ──
    if data.startswith("pay_telebirr_"):
        pk   = data[13:]
        plan = PLANS.get(pk)
        await q.edit_message_text(
            f"📱 *الدفع عبر TeleBirr*\n\n"
            f"1️⃣ افتح تطبيق TeleBirr\n"
            f"2️⃣ أرسل *{plan['etb']} ETB* إلى:\n"
            f"📞 `{TELEBIRR_NUMBER}`\n"
            f"3️⃣ اكتب في الملاحظة رقمك: `{u.id}`\n"
            f"4️⃣ بعد الدفع اضغط الزر أدناه ✅",
            reply_markup=kb_paid(pk),
            parse_mode="Markdown"
        )
        return

    # ── TON ──
    if data.startswith("pay_ton_"):
        pk   = data[8:]
        plan = PLANS.get(pk)
        await q.edit_message_text(
            f"💎 *الدفع عبر TON Wallet*\n\n"
            f"1️⃣ افتح محفظة TON\n"
            f"2️⃣ أرسل ما يعادل *{plan['usd']}$* إلى:\n"
            f"`{TON_WALLET}`\n"
            f"3️⃣ اكتب في الملاحظة: `{u.id}`\n"
            f"4️⃣ بعد الدفع اضغط ✅",
            reply_markup=kb_paid(pk),
            parse_mode="Markdown"
        )
        return

    # ── Binance ──
    if data.startswith("pay_binance_"):
        pk   = data[12:]
        plan = PLANS.get(pk)
        await q.edit_message_text(
            f"🔶 *الدفع عبر Binance Pay*\n\n"
            f"1️⃣ افتح Binance → Pay\n"
            f"2️⃣ أرسل *{plan['usd']}$* إلى UID:\n"
            f"`{BINANCE_UID}`\n"
            f"3️⃣ اكتب في الملاحظة: `{u.id}`\n"
            f"4️⃣ بعد الدفع اضغط ✅",
            reply_markup=kb_paid(pk),
            parse_mode="Markdown"
        )
        return

    # ── تأكيد الدفع ──
    if data.startswith("sent_"):
        pk   = data[5:]
        plan = PLANS.get(pk)
        conn = sqlite3.connect("bot.db")
        conn.execute(
            "INSERT INTO payments (user_id,plan,method,status,created_at) VALUES (?,?,?,?,?)",
            (u.id, pk, "manual", "pending", datetime.now().isoformat())
        )
        conn.commit(); conn.close()
        await q.edit_message_text(
            f"✅ شكراً يا {name}!\n"
            f"تم إرسال طلبك للمراجعة.\n"
            f"سيتم تفعيل اشتراكك خلال دقائق ⏳"
        )
        if OWNER_ID:
            await ctx.bot.send_message(
                OWNER_ID,
                f"💰 *طلب دفع جديد!*\n\n"
                f"👤 {name} (@{u.username})\n"
                f"🆔 ID: `{u.id}`\n"
                f"📦 الخطة: {plan['label']}\n"
                f"💵 {plan['usd']}$ / {plan['etb']} ETB\n\n"
                f"لتفعيل الاشتراك:\n"
                f"`/givepremium {u.id} {plan['days']}`",
                parse_mode="Markdown"
            )
        return

# ─── التشغيل ─────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("language",     cmd_language))
    app.add_handler(CommandHandler("premium",      cmd_premium))
    app.add_handler(CommandHandler("stats",        cmd_stats))
    app.add_handler(CommandHandler("givepremium",  cmd_givepremium))
    app.add_handler(CommandHandler("ban",          cmd_ban))
    app.add_handler(CommandHandler("broadcast",    cmd_broadcast))
    app.add_handler(CallbackQueryHandler(handle_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("✅ البوت يعمل!")
    app.run_polling()

if __name__ == "__main__":
    main()
