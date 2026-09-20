import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================================================
# НАЛАШТУВАННЯ
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

# Поки ID групи менеджерів невідомий, змінна може бути порожньою.
MANAGER_CHAT_ID = os.environ.get("MANAGER_CHAT_ID", "")

# Канал магазину
SHOP_CHANNEL = "@vylkashop"

# Адреса нашого сервісу Render
RENDER_URL = "https://vylkashop-orders-bot.onrender.com"

# Telegram Bot API
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Запам'ятовуємо, який товар обрав покупець.
# Для тестової версії цього достатньо.
customer_products = {}


# =========================================================
# ФУНКЦІЇ TELEGRAM
# =========================================================

def telegram(method, data):
    try:
        response = requests.post(
            f"{BOT_API}/{method}",
            json=data,
            timeout=20
        )

        result = response.json()

        print(f"Telegram {method}: {result}")

        return result

    except Exception as error:
        print(f"Telegram API error: {error}")

        return {
            "ok": False,
            "error": str(error)
        }


def send_message(chat_id, text, reply_markup=None):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup:
        data["reply_markup"] = reply_markup

    return telegram(
        "sendMessage",
        data
    )


def copy_product(to_chat_id, message_id):
    """
    Копіює оригінальний товарний пост
    із Telegram-каналу VYLKA.SHOP.
    """

    return telegram(
        "copyMessage",
        {
            "chat_id": to_chat_id,
            "from_chat_id": SHOP_CHANNEL,
            "message_id": message_id
        }
    )


# =========================================================
# ПЕРЕВІРКА RENDER
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return "VYLKA.SHOP bot is running", 200


# =========================================================
# НАЛАШТУВАННЯ TELEGRAM WEBHOOK
# =========================================================

@app.route("/setup-webhook", methods=["GET"])
def setup_webhook():

    webhook_url = f"{RENDER_URL}/webhook"

    result = telegram(
        "setWebhook",
        {
            "url": webhook_url
        }
    )

    return jsonify(result), 200


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route("/webhook", methods=["POST"])
def webhook():

    update = request.get_json(silent=True) or {}

    print("UPDATE:", update)

    message = update.get("message")

    # Поки що обробляємо звичайні повідомлення.
    if not message:
        return "OK", 200

    chat = message.get("chat", {})

    chat_id = chat.get("id")
    chat_type = chat.get("type")

    if not chat_id:
        return "OK", 200

    text = message.get("text", "")


    # =====================================================
    # КОМАНДА /chatid
    # =====================================================

    if text.startswith("/chatid"):

        send_message(
            chat_id,
            f"ID цього чату:\n{chat_id}"
        )

        return "OK", 200


    # =====================================================
    # ПРИВАТНИЙ ЧАТ ПОКУПЦЯ З БОТОМ
    # =====================================================

    if chat_type == "private":

        # -------------------------------------------------
        # ПОКУПЕЦЬ ПЕРЕЙШОВ ІЗ КНОПКИ ТОВАРУ
        #
        # Наприклад:
        #
        # https://t.me/vylkashop_orders_bot?start=post_7
        #
        # Telegram передасть боту:
        #
        # /start post_7
        # -------------------------------------------------

        if text.startswith("/start"):

            parts = text.split(maxsplit=1)

            # Перевіряємо, чи є параметр після /start
            if len(parts) == 2:

                parameter = parts[1]

                if parameter.startswith("post_"):

                    try:

                        post_id = int(
                            parameter.replace(
                                "post_",
                                "",
                                1
                            )
                        )

                    except ValueError:

                        post_id = None


                    if post_id:

                        # Запам'ятовуємо вибраний товар
                        customer_products[chat_id] = post_id

                        # Копіюємо сам товар покупцеві
                        copy_result = copy_product(
                            chat_id,
                            post_id
                        )

                        if copy_result.get("ok"):

                            send_message(
                                chat_id,
                                "👋 Ви обрали цей товар.\n\n"
                                "Напишіть ваше запитання "
                                "або повідомлення для менеджера."
                            )

                        else:

                            send_message(
                                chat_id,
                                "⚠️ Не вдалося показати товар.\n\n"
                                "Будь ласка, напишіть менеджеру."
                            )

                        return "OK", 200


            # Якщо користувач просто натиснув START
            # без конкретного товару

            send_message(
                chat_id,
                "👋 Вітаємо у VYLKA.SHOP!\n\n"
                "Оберіть потрібний товар у нашому "
                "Telegram-каналі та натисніть кнопку "
                "«🛒 Запитати / Замовити»."
            )

            return "OK", 200


        # =================================================
        # ПОКУПЕЦЬ НАПИСАВ ПОВІДОМЛЕННЯ
        # =================================================

        post_id = customer_products.get(chat_id)

        user = message.get("from", {})

        first_name = user.get(
            "first_name",
            "Покупець"
        )

        username = user.get("username")

        customer_name = first_name

        if username:
            customer_name += f" (@{username})"


        # =================================================
        # ЯКЩО ГРУПА МЕНЕДЖЕРІВ ЩЕ НЕ НАЛАШТОВАНА
        # =================================================

        if not MANAGER_CHAT_ID:

            send_message(
                chat_id,
                "Дякуємо за повідомлення.\n\n"
                "Система зв'язку з менеджером "
                "зараз налаштовується."
            )

            return "OK", 200


        # =================================================
        # КОПІЮЄМО ТОВАР У ГРУПУ МЕНЕДЖЕРІВ
        # =================================================

        if post_id:

            copy_product(
                MANAGER_CHAT_ID,
                post_id
            )


        # =================================================
        # ФОРМУЄМО ПОВІДОМЛЕННЯ ДЛЯ МЕНЕДЖЕРА
        # =================================================

        manager_text = (
            "🛍 НОВЕ ЗВЕРНЕННЯ\n\n"
            f"👤 Покупець: {customer_name}\n"
            f"🆔 Telegram ID: {chat_id}\n"
        )

        if post_id:

            manager_text += (
                f"📦 Товар: пост №{post_id}\n"
            )

        manager_text += (
            "\n💬 Повідомлення покупця:\n"
        )

        if text:

            manager_text += text

        else:

            manager_text += (
                "[Покупець надіслав медіа "
                "або інший тип повідомлення]"
            )


        # =================================================
        # НАДСИЛАЄМО ЗВЕРНЕННЯ МЕНЕДЖЕРУ
        # =================================================

        send_message(
            MANAGER_CHAT_ID,
            manager_text
        )


        # =================================================
        # ПІДТВЕРДЖЕННЯ ПОКУПЦЕВІ
        # =================================================

        send_message(
            chat_id,
            "✅ Ваше повідомлення передано менеджеру."
        )

        return "OK", 200


    # =====================================================
    # ІНШІ ПОВІДОМЛЕННЯ
    # =====================================================

    return "OK", 200


# =========================================================
# ЗАПУСК FLASK
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
