"""
Vercel Telegram Live-Relay Bot
File: api/bot.py

ONE-FILE deployment:
    repo/
      api/
        bot.py

No third-party Python packages required.

Environment variables:
    BOT_TOKEN                  Required
    ADMIN_ID                   Required
    FORCE_JOIN_CHANNEL         Optional, e.g. @Shreewin028
    FORCE_JOIN_URL             Optional, e.g. https://t.me/Shreewin028
    REGISTER_URL               Optional
    PROOF_URL                  Optional
    WEBHOOK_SECRET             Recommended
    UPSTASH_REDIS_REST_URL     Required for persistent users/stats
    UPSTASH_REDIS_REST_TOKEN   Required for persistent users/stats
    PUBLIC_URL                 Optional. Otherwise Vercel URL is detected.
    WELCOME_IMAGE_FILE_ID      Optional; can also be configured with /setwelcomeimage
    BOT_NAME                   Optional

Important:
- Do NOT hard-code your Telegram bot token.
- Revoke any token that has been publicly exposed.
- copyMessage is deliberately used for relay/reply. This preserves Telegram
  media and message entities, including custom emoji, instead of downloading
  and re-uploading content.
"""

import json
import os
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0") or "0")

FORCE_JOIN_CHANNEL = os.environ.get("FORCE_JOIN_CHANNEL", "@Shreewin028").strip()
FORCE_JOIN_URL = os.environ.get(
    "FORCE_JOIN_URL", "https://t.me/Shreewin028"
).strip()

REGISTER_URL = os.environ.get(
    "REGISTER_URL",
    "https://www.veergame13.com/#/register?invitationCode=27164120753",
).strip()

PROOF_URL = os.environ.get(
    "PROOF_URL", "https://t.me/Shreewin87"
).strip()

BOT_NAME = os.environ.get("BOT_NAME", "ALEX PRIDICTION").strip()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").strip()

WELCOME_IMAGE_FILE_ID = os.environ.get("WELCOME_IMAGE_FILE_ID", "").strip()

REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip()
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()

WELCOME_TEXT = f"""🎉 <b>WELCOME TO {BOT_NAME}</b>

DAILY DEPOSIT KARO 1000+ AUR DAILY UID AND DEPOSIT HISTORY DO AAPKO DAILY SPECIAL GIFT CODE 🎁 MILEGA

PROOF <a href="{PROOF_URL}">➡️ @Shreewin87</a> ✅

NOTE: MERE LINK SE UID HONA CHAIYE

<b>𝐎𝐅𝐅𝐈𝐂𝐈𝐀𝐋 𝐑𝐄𝐆𝐈𝐒𝐓𝐄𝐑 𝐋𝐈𝐍𝐊 📌</b>:
<a href="{REGISTER_URL}">REGISTER NOW</a>

We play on the edge. 🛑 <b>18+ Only.</b> Join at your own RISK."""

# Redis keys
K_USERS = "alexbot:users"
K_MESSAGES = "alexbot:message_map"
K_STATS = "alexbot:stats"
K_STATE = "alexbot:state"
K_CONFIG = "alexbot:config"


# ---------------------------------------------------------------------------
# Minimal Redis REST client
# ---------------------------------------------------------------------------

def redis_available():
    return bool(REDIS_URL and REDIS_TOKEN)


def redis_command(*parts):
    """Execute one Redis command through Upstash REST."""
    if not redis_available():
        return None

    url = REDIS_URL.rstrip("/") + "/"
    payload = json.dumps(list(parts)).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {REDIS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=8) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
            return result.get("result")
    except Exception:
        return None


def r_set(key, value):
    return redis_command("SET", key, value)


def r_get(key):
    return redis_command("GET", key)


def r_sadd(key, value):
    return redis_command("SADD", key, value)


def r_smembers(key):
    result = redis_command("SMEMBERS", key)
    return result if isinstance(result, list) else []


def r_hset(key, field, value):
    return redis_command("HSET", key, field, value)


def r_hget(key, field):
    return redis_command("HGET", key, field)


def r_hincrby(key, field, amount=1):
    return redis_command("HINCRBY", key, field, str(amount))


def r_incr(key):
    return redis_command("INCR", key)


def r_del(key):
    return redis_command("DEL", key)


# ---------------------------------------------------------------------------
# Telegram Bot API
# ---------------------------------------------------------------------------

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def tg(method, data=None):
    """Call a Telegram Bot API method with JSON data."""
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    payload = json.dumps(data or {}).encode("utf-8")
    req = Request(
        f"{API}/{method}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw)
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8")
            result = json.loads(raw)
        except Exception:
            result = {"ok": False, "description": str(exc)}
    except (URLError, TimeoutError) as exc:
        result = {"ok": False, "description": str(exc)}

    return result


def tg_ok(method, data=None):
    result = tg(method, data)
    return bool(result.get("ok")), result


def send_message(chat_id, text, reply_markup=None, reply_to=None, parse_mode="HTML"):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        data["reply_markup"] = reply_markup
    if reply_to is not None:
        data["reply_parameters"] = {"message_id": reply_to}
    return tg("sendMessage", data)


def answer_callback(callback_id, text=None, show_alert=False):
    data = {"callback_query_id": callback_id}
    if text:
        data["text"] = text
    if show_alert:
        data["show_alert"] = True
    return tg("answerCallbackQuery", data)


def edit_message(chat_id, message_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        data["reply_markup"] = reply_markup
    return tg("editMessageText", data)


def copy_message(target_chat_id, from_chat_id, message_id, reply_markup=None):
    data = {
        "chat_id": target_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
    }
    if reply_markup is not None:
        data["reply_markup"] = reply_markup
    return tg("copyMessage", data)


# ---------------------------------------------------------------------------
# Inline keyboard helpers
# ---------------------------------------------------------------------------

def button(text, callback_data=None, url=None, style=None):
    item = {"text": text}
    if callback_data is not None:
        item["callback_data"] = callback_data
    if url is not None:
        item["url"] = url
    if style in ("primary", "success", "danger"):
        # Supported by newer Bot API clients.
        item["style"] = style
    return item


def welcome_keyboard():
    return {
        "inline_keyboard": [
            [
                button("🎁 Register Now", url=REGISTER_URL, style="success"),
                button("📢 Proof", url=PROOF_URL, style="primary"),
            ],
            [
                button("💬 Contact Admin", callback_data="contact_admin", style="primary"),
                button("ℹ️ About", callback_data="about", style="primary"),
            ],
            [
                button("🆘 Help", callback_data="help", style="danger"),
            ],
        ]
    }


def join_keyboard():
    return {
        "inline_keyboard": [
            [button("📢 JOIN CHANNEL", url=FORCE_JOIN_URL, style="primary")],
            [button("✅ I JOINED — CHECK", callback_data="check_join", style="success")],
        ]
    }


def admin_keyboard():
    return {
        "inline_keyboard": [
            [
                button("📊 Stats", callback_data="admin_stats", style="primary"),
                button("❤️ Health", callback_data="admin_health", style="success"),
            ],
            [
                button("📣 Broadcast", callback_data="admin_broadcast", style="primary"),
                button("🖼 Welcome Image", callback_data="admin_welcome_image", style="primary"),
            ],
            [
                button("⚙️ Webhook", callback_data="admin_webhook", style="primary"),
                button("🆘 Help", callback_data="admin_help", style="danger"),
            ],
        ]
    }


# ---------------------------------------------------------------------------
# Persistence/state
# ---------------------------------------------------------------------------

def user_add(user):
    if not user:
        return
    uid = str(user.get("id"))
    r_sadd(K_USERS, uid)
    r_hset(
        f"alexbot:user:{uid}",
        "first_name",
        user.get("first_name", ""),
    )
    r_hset(
        f"alexbot:user:{uid}",
        "last_name",
        user.get("last_name", ""),
    )
    r_hset(
        f"alexbot:user:{uid}",
        "username",
        user.get("username", ""),
    )


def users():
    return [int(x) for x in r_smembers(K_USERS) if str(x).lstrip("-").isdigit()]


def stat_inc(name, amount=1):
    r_hincrby(K_STATS, name, amount)


def stat_get(name):
    value = r_hget(K_STATS, name)
    try:
        return int(value or 0)
    except Exception:
        return 0


def save_message_map(admin_message_id, user_id):
    r_hset(K_MESSAGES, str(admin_message_id), str(user_id))


def get_message_user(admin_message_id):
    value = r_hget(K_MESSAGES, str(admin_message_id))
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def set_pending_reply(admin_id, user_id):
    r_hset(K_STATE, f"reply:{admin_id}", str(user_id))


def get_pending_reply(admin_id):
    value = r_hget(K_STATE, f"reply:{admin_id}")
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def clear_pending_reply(admin_id):
    redis_command("HDEL", K_STATE, f"reply:{admin_id}")


def set_broadcast_mode(admin_id, enabled=True):
    r_hset(K_STATE, f"broadcast:{admin_id}", "1" if enabled else "0")


def broadcast_mode(admin_id):
    return r_hget(K_STATE, f"broadcast:{admin_id}") == "1"


def set_config(name, value):
    r_hset(K_CONFIG, name, value)


def get_config(name):
    return r_hget(K_CONFIG, name)


# ---------------------------------------------------------------------------
# Access / membership
# ---------------------------------------------------------------------------

def is_admin(user_id):
    return int(user_id or 0) == ADMIN_ID


def joined_required_channel(user_id):
    if not FORCE_JOIN_CHANNEL:
        return True

    result = tg("getChatMember", {
        "chat_id": FORCE_JOIN_CHANNEL,
        "user_id": user_id,
    })

    if not result.get("ok"):
        # If the bot cannot inspect membership, fail closed for force-join.
        return False

    member = result.get("result", {})
    status = member.get("status")

    if status in ("creator", "administrator", "member"):
        return True

    if status == "restricted":
        return bool(member.get("is_member"))

    return False


def force_join_message(chat_id):
    return send_message(
        chat_id,
        "🔒 <b>CHANNEL JOIN REQUIRED</b>\n\n"
        "Please join the required channel first, then tap "
        "<b>✅ I JOINED — CHECK</b>.",
        reply_markup=join_keyboard(),
    )


# ---------------------------------------------------------------------------
# Welcome/config
# ---------------------------------------------------------------------------

def welcome_image():
    return get_config("welcome_image") or WELCOME_IMAGE_FILE_ID


def send_welcome(chat_id):
    image_id = welcome_image()

    if image_id:
        result = tg("sendPhoto", {
            "chat_id": chat_id,
            "photo": image_id,
            "caption": WELCOME_TEXT,
            "parse_mode": "HTML",
            "reply_markup": welcome_keyboard(),
        })
        if result.get("ok"):
            return result

    return send_message(
        chat_id,
        WELCOME_TEXT,
        reply_markup=welcome_keyboard(),
    )


# ---------------------------------------------------------------------------
# Admin message formatting
# ---------------------------------------------------------------------------

def admin_user_card(user):
    uid = user.get("id")
    first = user.get("first_name", "") or ""
    last = user.get("last_name", "") or ""
    username = user.get("username")
    full = " ".join(x for x in [first, last] if x).strip() or "Unknown"

    username_line = f"@{username}" if username else "No username"

    text = (
        "📥 <b>NEW USER MESSAGE</b>\n\n"
        f"👤 <b>Name:</b> {escape_html(full)}\n"
        f"🔹 <b>Username:</b> {escape_html(username_line)}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n\n"
        "↳ Reply directly to the copied message below to answer this user."
    )

    return text


def escape_html(value):
    value = str(value)
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def admin_reply_button(user_id):
    return {
        "inline_keyboard": [
            [button(
                "💬 Reply to User",
                callback_data=f"reply:{user_id}",
                style="success",
            )],
        ]
    }


# ---------------------------------------------------------------------------
# Relay logic
# ---------------------------------------------------------------------------

def relay_user_message(message):
    user = message.get("from") or {}
    chat = message.get("chat") or {}
    user_id = user.get("id")
    source_chat = chat.get("id")
    message_id = message.get("message_id")

    if not user_id or not message_id:
        return

    user_add(user)
    stat_inc("messages_received")

    # Admin gets a small metadata header.
    header = send_message(
        ADMIN_ID,
        admin_user_card(user),
        reply_markup=admin_reply_button(user_id),
    )

    # Then copy the ORIGINAL Telegram message.
    # This preserves:
    # - custom emoji entities
    # - premium emoji sent by the user
    # - photos
    # - videos
    # - voice messages
    # - audio/music
    # - documents
    # - GIF/animation
    # - stickers, including animated/video stickers
    # - video notes
    # - captions and caption entities
    # - other copyable message types supported by Telegram
    copied = copy_message(ADMIN_ID, source_chat, message_id)

    if copied.get("ok"):
        copied_message_id = copied["result"]["message_id"]
        save_message_map(copied_message_id, int(user_id))
        stat_inc("messages_copied_to_admin")
    else:
        # If Telegram cannot copy a particular service/non-copyable message,
        # still tell admin who sent it.
        send_message(
            ADMIN_ID,
            "⚠️ Telegram could not copy this message type automatically.\n"
            f"User ID: <code>{user_id}</code>",
            reply_markup=admin_reply_button(user_id),
        )


def relay_admin_reply(message, target_user_id):
    if not target_user_id:
        return False

    # copyMessage preserves custom emoji/media/entities from the admin's
    # original message. The user sees the content as coming from the bot.
    result = copy_message(
        target_user_id,
        ADMIN_ID,
        message.get("message_id"),
    )

    if result.get("ok"):
        stat_inc("admin_replies_sent")
        return True

    send_message(
        ADMIN_ID,
        "❌ I could not send that message to the user.\n"
        "Telegram may classify this as a non-copyable/service message.",
    )
    return False


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------

def start_broadcast(admin_id):
    set_broadcast_mode(admin_id, True)
    return send_message(
        admin_id,
        "📣 <b>BROADCAST MODE</b>\n\n"
        "Send or reply with the message/media you want to broadcast.\n\n"
        "The bot will copy the message to all registered users.\n\n"
        "Use /cancel to stop.",
    )


def run_broadcast(message):
    targets = users()
    success = 0
    failed = 0

    send_message(
        ADMIN_ID,
        f"📣 Broadcasting to <b>{len(targets)}</b> users...",
    )

    for uid in targets:
        result = copy_message(
            uid,
            ADMIN_ID,
            message.get("message_id"),
        )
        if result.get("ok"):
            success += 1
        else:
            failed += 1

        # Small delay prevents an unnecessary burst on small bots.
        time.sleep(0.04)

    set_broadcast_mode(ADMIN_ID, False)

    send_message(
        ADMIN_ID,
        "✅ <b>BROADCAST FINISHED</b>\n\n"
        f"👥 Total: <code>{len(targets)}</code>\n"
        f"✅ Sent: <code>{success}</code>\n"
        f"❌ Failed: <code>{failed}</code>",
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

HELP_TEXT = """🆘 <b>HELP</b>

<b>User commands</b>
/start — Open welcome page
/about — About the bot
/help — Help

<b>Admin commands</b>
/admin — Admin panel
/stats — Bot statistics
/broadcast — Broadcast a message
/setwelcomeimage — Set welcome image
/setwebhook — Register Telegram webhook
/setcommands — Refresh command menu
/health — System/API health
/cancel — Cancel current admin mode

<b>Message support</b>
Users can send text, photos, videos, voice messages, audio/music, documents, animations/GIFs, stickers, video stickers, video notes and other Telegram message types supported by copyMessage.

Admin can reply directly to the copied user message or use the <b>💬 Reply to User</b> button."""

ABOUT_TEXT = """ℹ️ <b>ABOUT</b>

This is a custom Telegram support/relay bot.

👤 User messages → Admin
💬 Admin replies → User
🖼 Media relay
🎤 Voice relay
🎵 Audio relay
🎬 Video relay
📁 Document relay
🎞 GIF/animation relay
🎨 Sticker relay
😀 Custom emoji preservation

All relay operations use Telegram's message-copy functionality where possible, so the bot does not need to download user media to your Vercel filesystem."""


def stats_text():
    return (
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Registered users: <code>{len(users())}</code>\n"
        f"📥 Messages received: <code>{stat_get('messages_received')}</code>\n"
        f"📤 Messages copied to admin: <code>{stat_get('messages_copied_to_admin')}</code>\n"
        f"💬 Admin replies: <code>{stat_get('admin_replies_sent')}</code>\n"
        f"🚀 Broadcasts sent: <code>{stat_get('broadcast_sent')}</code>"
    )


def health_text():
    redis_state = "✅ Connected" if redis_available() and r_get("alexbot:health_test") is not None else "⚠️ Check config"

    # Create/update a lightweight Redis health key.
    if redis_available():
        r_set("alexbot:health_test", "ok")
        redis_state = "✅ Connected"

    return (
        "❤️ <b>BOT HEALTH</b>\n\n"
        "🤖 Telegram API: configured\n"
        f"💾 Redis: {redis_state}\n"
        f"🔐 Webhook secret: {'configured' if WEBHOOK_SECRET else 'not configured'}\n"
        f"📡 Force join: {'enabled' if FORCE_JOIN_CHANNEL else 'disabled'}"
    )


def setup_commands():
    commands = [
        {"command": "start", "description": "Open welcome page"},
        {"command": "about", "description": "About the bot"},
        {"command": "help", "description": "Show help"},
        {"command": "admin", "description": "Admin panel"},
        {"command": "stats", "description": "Bot statistics"},
        {"command": "broadcast", "description": "Broadcast message"},
        {"command": "health", "description": "Bot health"},
        {"command": "setwelcomeimage", "description": "Set welcome image"},
        {"command": "setwebhook", "description": "Set Telegram webhook"},
        {"command": "setcommands", "description": "Refresh bot commands"},
        {"command": "cancel", "description": "Cancel admin mode"},
    ]
    return tg("setMyCommands", {"commands": commands})


def set_webhook():
    public = os.environ.get("PUBLIC_URL", "").strip()

    if not public:
        # Vercel exposes VERCEL_URL as the deployment hostname.
        host = os.environ.get("VERCEL_URL", "").strip()
        if host:
            public = f"https://{host}/api/bot"

    if public and not public.endswith("/api/bot"):
        public = public.rstrip("/") + "/api/bot"

    if not public:
        return {
            "ok": False,
            "description": "Set PUBLIC_URL or deploy on Vercel with VERCEL_URL available.",
        }

    data = {
        "url": public,
        "drop_pending_updates": False,
    }

    if WEBHOOK_SECRET:
        data["secret_token"] = WEBHOOK_SECRET

    result = tg("setWebhook", data)

    if result.get("ok"):
        set_config("webhook_url", public)

    return result


# ---------------------------------------------------------------------------
# Update handlers
# ---------------------------------------------------------------------------

def handle_start(message):
    chat_id = message["chat"]["id"]
    user = message.get("from") or {}
    user_add(user)

    if is_admin(user.get("id")):
        return send_welcome(chat_id)

    if not joined_required_channel(user.get("id")):
        return force_join_message(chat_id)

    return send_welcome(chat_id)


def handle_callback(callback):
    callback_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    from_user = callback.get("from") or {}
    actor_id = from_user.get("id")

    if data == "check_join":
        if joined_required_channel(actor_id):
            answer_callback(callback_id, "✅ Membership verified!")
            send_welcome(chat_id)
        else:
            answer_callback(
                callback_id,
                "❌ You haven't joined the required channel yet.",
                True,
            )
        return

    if data == "about":
        answer_callback(callback_id)
        send_message(chat_id, ABOUT_TEXT)
        return

    if data == "help":
        answer_callback(callback_id)
        send_message(chat_id, HELP_TEXT)
        return

    if data == "contact_admin":
        answer_callback(callback_id)
        send_message(
            chat_id,
            "💬 <b>Contact Admin</b>\n\n"
            "Send your message here and it will be delivered to the admin.",
        )
        return

    if not is_admin(actor_id):
        answer_callback(callback_id, "⛔ Admin only.", True)
        return

    if data.startswith("reply:"):
        target = data.split(":", 1)[1]
        if target.isdigit():
            set_pending_reply(actor_id, int(target))
            answer_callback(callback_id, "Reply mode enabled.")
            send_message(
                chat_id,
                f"✍️ <b>REPLY MODE</b>\n\n"
                f"Target User ID: <code>{target}</code>\n\n"
                "Send your next message. It will be delivered to this user.\n"
                "Use /cancel to stop.",
            )
        return

    if data == "admin_stats":
        answer_callback(callback_id)
        send_message(chat_id, stats_text(), reply_markup=admin_keyboard())
        return

    if data == "admin_health":
        answer_callback(callback_id)
        send_message(chat_id, health_text(), reply_markup=admin_keyboard())
        return

    if data == "admin_broadcast":
        answer_callback(callback_id)
        start_broadcast(actor_id)
        return

    if data == "admin_welcome_image":
        answer_callback(callback_id)
        send_message(
            chat_id,
            "🖼 <b>WELCOME IMAGE</b>\n\n"
            "Send a photo now.\n"
            "The bot will save Telegram's file_id and use that photo on /start.\n\n"
            "Use /cancel to stop.",
        )
        r_hset(K_STATE, f"image:{actor_id}", "1")
        return

    if data == "admin_webhook":
        answer_callback(callback_id)
        result = set_webhook()
        if result.get("ok"):
            send_message(chat_id, "✅ Webhook registered successfully.")
        else:
            send_message(
                chat_id,
                "❌ Webhook registration failed:\n"
                f"<code>{escape_html(result.get('description', 'Unknown error'))}</code>",
            )
        return

    if data == "admin_help":
        answer_callback(callback_id)
        send_message(chat_id, HELP_TEXT, reply_markup=admin_keyboard())
        return

    answer_callback(callback_id)


def handle_command(message, command, args):
    chat_id = message["chat"]["id"]
    user_id = message.get("from", {}).get("id")

    if command == "/start":
        return handle_start(message)

    if command == "/about":
        return send_message(chat_id, ABOUT_TEXT)

    if command == "/help":
        return send_message(chat_id, HELP_TEXT)

    if command == "/cancel":
        if is_admin(user_id):
            clear_pending_reply(user_id)
            set_broadcast_mode(user_id, False)
            redis_command("HDEL", K_STATE, f"image:{user_id}")
            return send_message(chat_id, "✅ Current admin mode cancelled.")
        return

    if not is_admin(user_id):
        return send_message(chat_id, "⛔ This command is available to the admin only.")

    if command == "/admin":
        return send_message(
            chat_id,
            "🛠 <b>ADMIN PANEL</b>\n\nChoose an action:",
            reply_markup=admin_keyboard(),
        )

    if command == "/stats":
        return send_message(chat_id, stats_text())

    if command == "/health":
        return send_message(chat_id, health_text())

    if command == "/broadcast":
        return start_broadcast(user_id)

    if command == "/setwelcomeimage":
        r_hset(K_STATE, f"image:{user_id}", "1")
        return send_message(
            chat_id,
            "🖼 Send the welcome photo now.\n\nUse /cancel to stop.",
        )

    if command == "/setwebhook":
        result = set_webhook()
        if result.get("ok"):
            return send_message(chat_id, "✅ Webhook registered successfully.")
        return send_message(
            chat_id,
            "❌ Webhook error:\n"
            f"<code>{escape_html(result.get('description', 'Unknown error'))}</code>",
        )

    if command == "/setcommands":
        result = setup_commands()
        return send_message(
            chat_id,
            "✅ Commands updated." if result.get("ok") else "❌ Could not update commands.",
        )

    return send_message(chat_id, "Unknown command. Use /help.")


def handle_message(message):
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    user = message.get("from") or {}
    user_id = user.get("id")

    if not chat_id or not user_id:
        return

    # This bot is intended for private support chats.
    if chat.get("type") != "private":
        return

    # Admin-specific states take priority.
    if is_admin(user_id):
        # Set welcome image mode
        if r_hget(K_STATE, f"image:{user_id}") == "1":
            photo = message.get("photo")
            if photo:
                file_id = photo[-1].get("file_id")
                set_config("welcome_image", file_id)
                redis_command("HDEL", K_STATE, f"image:{user_id}")
                send_message(
                    chat_id,
                    "✅ Welcome image saved.\n\n"
                    "Use /start to preview it.",
                )
                return

        # Broadcast mode
        if broadcast_mode(user_id):
            if message.get("text", "").strip() == "/cancel":
                set_broadcast_mode(user_id, False)
                send_message(chat_id, "✅ Broadcast cancelled.")
                return

            run_broadcast(message)
            stat_inc("broadcast_sent")
            return

        # Reply mode from inline button
        pending = get_pending_reply(user_id)
        if pending:
            if message.get("text", "").strip() == "/cancel":
                clear_pending_reply(user_id)
                send_message(chat_id, "✅ Reply mode cancelled.")
                return

            if relay_admin_reply(message, pending):
                clear_pending_reply(user_id)
                send_message(
                    chat_id,
                    f"✅ Sent to user <code>{pending}</code>.",
                )
            return

        # Direct reply to a copied user message.
        reply = message.get("reply_to_message")
        if reply:
            target = get_message_user(reply.get("message_id"))
            if target:
                relay_admin_reply(message, target)
                return

        # Ordinary admin message: don't echo it to users.
        return

    # Regular user
    user_add(user)

    # Commands are handled before force-join.
    text = message.get("text", "")
    if text.startswith("/"):
        command = text.split()[0].split("@")[0].lower()
        args = text.split()[1:]
        handle_command(message, command, args)
        return

    # Enforce join for support messages.
    if not joined_required_channel(user_id):
        force_join_message(chat_id)
        return

    relay_user_message(message)


def handle_update(update):
    if "callback_query" in update:
        handle_callback(update["callback_query"])
        return

    message = update.get("message")
    if message:
        handle_message(message)
        return

    # Edited messages, channel posts, etc. can be ignored safely for this
    # private support-bot workflow.


# ---------------------------------------------------------------------------
# Vercel HTTP Function
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):

    def _send(self, status, body):
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        # Useful for Vercel health checks.
        self._send(
            200,
            json.dumps({
                "ok": True,
                "service": "telegram-live-relay",
                "webhook": True,
            }),
        )

    def do_POST(self):
        # Telegram webhook secret verification.
        if WEBHOOK_SECRET:
            received = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if received != WEBHOOK_SECRET:
                self._send(403, json.dumps({"ok": False, "error": "forbidden"}))
                return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            update = json.loads(body.decode("utf-8"))

            handle_update(update)

            self._send(200, json.dumps({"ok": True}))
        except Exception as exc:
            # Always return quickly to Telegram; detailed traceback goes to
            # Vercel logs.
            print("Webhook error:", repr(exc))
            traceback.print_exc()
            self._send(200, json.dumps({"ok": True}))


# Vercel may inspect this value if configured through vercel.json.
maxDuration = 30
