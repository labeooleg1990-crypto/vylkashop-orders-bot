import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =========================================================
# НАЛАШТУВАННЯ
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

MANAGER_CHAT_ID = os.environ.get(
    "MANAGER_CHAT_ID",
    "-1004323796567"
)

SHOP_CHANNEL = "@vylkashop"

RENDER_URL = "https://vylkashop-orders-bot.onrender.com"

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# =========================================================
# ТИМЧАСОВЕ СХОВИЩЕ
# =========================================================

# Який товар зараз вибрав покупець
customer_products = {}

# customer_id -> topic_id
customer_topics = {}

# topic_id -> customer_id
topic_customers = {}

# Запам'ятовуємо, чи вже показували товар менеджеру
product_sent_to_topic = {}


# =========================================================
# TELEGRAM API
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


def send_message(
    chat_id,
    text,
    message_thread_id=None
):

    data = {
        "chat_id": chat_id,
        "text": text
    }

    if message_thread_id:
        data["message_thread_id"] = message_thread_id

    return telegram(
        "sendMessage",
        data
    )


def copy_message(
    to_chat_id,
    from_chat_id,
    message_id,
    message_thread_id=None
):

    data = {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id
    }

    if message_thread_id:
        data["message_thread_id"] = message_thread_id

    return telegram(
        "copyMessage",
        data
    )


def copy_product(
    to_chat_id,
    post_id,
    message_thread_id=None
):

    return copy_message(
        to_chat_id,
        SHOP_CHANNEL,
        post_id,
        message_thread_id
    )


# =========================================================
# СТВОРЕННЯ ГІЛКИ ПОКУПЦЯ
# =========================================================

def create_customer_topic(customer_id, customer_name):

    # Якщо для цього покупця вже є гілка
    if customer_id in customer_topics:
        return customer_topics[customer_id]

    # Назва гілки
    topic_name = f"👤 {customer_name}"

    # Telegram має обмеження на довжину назви
    topic_name = topic_name[:120]

    result = telegram(
        "createForumTopic",
        {
            "chat_id": MANAGER_CHAT_ID,
            "name": topic_name
        }
    )

    if not result.get("ok"):

        print(
            "Не вдалося створити гілку:",
            result
        )

        return None

    topic_id = result["result"]["message_thread_id"]

    customer_topics[customer_id] = topic_id
    topic_customers[topic_id] = customer_id

    return topic_id


# =========================================================
# ГОЛОВНА СТОРІНКА
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return "VYLKA.SHOP bot is running", 200


# =========================================================
# WEBHOOK SETUP
# =========================================================

@app.route("/setup-webhook", methods=["GET"])
def setup_webhook():

    webhook_url = f"{RENDER_URL}/webhook"

    result = telegram(
        "setWebhook",
        {
            "url": webhook_url,
            "allowed_updates": [
                "message"
            ]
        }
    )

    return jsonify(result), 200


# =========================================================
# WEBHOOK
# =========================================================

@app.route("/webhook", methods=["POST"])
def webhook():

    update = request.get_json(silent=True) or {}

    print("UPDATE:", update)

    message = update.get("message")

    if not message:
        return "OK", 200


    # =====================================================
    # НЕ ОБРОБЛЯЄМО ВЛАСНІ ПОВІДОМЛЕННЯ БОТА
    # =====================================================

    sender = message.get("from", {})

    if sender.get("is_bot"):
        return "OK", 200


    chat = message.get("chat", {})

    chat_id = chat.get("id")
    chat_type = chat.get("type")

    if not chat_id:
        return "OK", 200

    text = message.get("text", "")


    # =====================================================
    # /chatid
    # =====================================================

    if text.startswith("/chatid"):

        send_message(
            chat_id,
            f"ID цього чату:\n{chat_id}"
        )

        return "OK", 200


    # =====================================================
    # ПРИВАТНИЙ ЧАТ ПОКУПЦЯ
    # =====================================================

    if chat_type == "private":

        customer_id = chat_id

        first_name = sender.get(
            "first_name",
            "Покупець"
        )

        username = sender.get("username")

        customer_name = first_name

        if username:
            customer_name += f" @{username}"


        # =================================================
        # START ІЗ КОНКРЕТНОГО ТОВАРУ
        # =================================================

        if text.startswith("/start"):

            parts = text.split(maxsplit=1)

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

                        # Запам'ятовуємо товар
                        customer_products[
                            customer_id
                        ] = post_id

                        # Показуємо покупцю товар
                        result = copy_product(
                            customer_id,
                            post_id
                        )

                        if result.get("ok"):

                            send_message(
                                customer_id,
                                "👋 Ви обрали цей товар.\n\n"
                                "Напишіть ваше запитання "
                                "або повідомлення для менеджера."
                            )

                        else:

                            send_message(
                                customer_id,
                                "⚠️ Не вдалося показати товар.\n\n"
                                "Напишіть повідомлення менеджеру."
                            )

                        return "OK", 200


            # START без товару

            send_message(
                customer_id,
                "👋 Вітаємо у VYLKA.SHOP!\n\n"
                "Оберіть потрібний товар у нашому "
                "Telegram-каналі та натисніть "
                "«🛒 Запитати / Замовити»."
            )

            return "OK", 200


        # =================================================
        # ПОВІДОМЛЕННЯ ПОКУПЦЯ
        # =================================================

        post_id = customer_products.get(
            customer_id
        )


        # Створюємо або знаходимо гілку покупця

        topic_id = create_customer_topic(
            customer_id,
            customer_name
        )


        # =================================================
        # ЯКЩО ГІЛКУ НЕ ВДАЛОСЯ СТВОРИТИ
        # =================================================

        if not topic_id:

            send_message(
                customer_id,
                "⚠️ Не вдалося передати повідомлення "
                "менеджеру.\n\n"
                "Спробуйте ще раз трохи пізніше."
            )

            return "OK", 200


        # =================================================
        # ПЕРШЕ ПОВІДОМЛЕННЯ У ГІЛЦІ
        # =================================================

        if customer_id not in product_sent_to_topic:

            # Інформація про покупця

            info = (
                "🛍 НОВЕ ЗВЕРНЕННЯ\n\n"
                f"👤 Покупець: {customer_name}\n"
                f"🆔 Telegram ID: {customer_id}"
            )

            send_message(
                MANAGER_CHAT_ID,
                info,
                topic_id
            )


            # Сам товар

            if post_id:

                copy_product(
                    MANAGER_CHAT_ID,
                    post_id,
                    topic_id
                )


            product_sent_to_topic[
                customer_id
            ] = True


        # =================================================
        # КОПІЮЄМО ПОВІДОМЛЕННЯ ПОКУПЦЯ
        # =================================================

        copy_result = copy_message(
            MANAGER_CHAT_ID,
            customer_id,
            message["message_id"],
            topic_id
        )


        # Якщо copyMessage не спрацював
        if not copy_result.get("ok") and text:

            send_message(
                MANAGER_CHAT_ID,
                f"💬 {text}",
                topic_id
            )


        # =================================================
        # ПІДТВЕРДЖЕННЯ ПОКУПЦЕВІ
        # =================================================

        send_message(
            customer_id,
            "✅ Повідомлення передано менеджеру."
        )

        return "OK", 200


    # =====================================================
    # ГРУПА МЕНЕДЖЕРІВ
    # =====================================================

    if str(chat_id) == str(MANAGER_CHAT_ID):

        # ID гілки, з якої пише менеджер
        topic_id = message.get(
            "message_thread_id"
        )

        # Якщо повідомлення написане не в гілці
        if not topic_id:
            return "OK", 200


        # Знаходимо покупця
        customer_id = topic_customers.get(
            topic_id
        )


        # Якщо ця гілка не пов'язана з покупцем
        if not customer_id:
            return "OK", 200


        # =================================================
        # ПЕРЕДАЄМО ПОВІДОМЛЕННЯ МЕНЕДЖЕРА ПОКУПЦЮ
        # =================================================

        result = copy_message(
            customer_id,
            MANAGER_CHAT_ID,
            message["message_id"]
        )


        # Якщо копіювання не вдалося,
        # пробуємо передати текст

        if not result.get("ok") and text:

            send_message(
                customer_id,
                f"💬 Менеджер VYLKA.SHOP:\n\n{text}"
            )


        return "OK", 200


    return "OK", 200


# =========================================================
# ЗАПУСК
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
