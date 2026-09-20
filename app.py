import os
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
MANAGER_CHAT_ID = os.environ["MANAGER_CHAT_ID"]

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Канал, з якого копіюємо товарні пости
SHOP_CHANNEL = "@vylkashop"

# Тут запам'ятовуємо, який товар вибрав покупець.
# Для першої версії достатньо; пізніше зробимо постійне зберігання.
customer_products = {}


def telegram(method, data):
    response = requests.post(f"{BOT_API}/{method}", json=data, timeout=20)
    return response.json()


def send_message(chat_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if reply_markup:
        data["reply_markup"] = reply_markup

    return telegram("sendMessage", data)


def copy_product(to_chat_id, message_id):
    return telegram(
        "copyMessage",
        {
            "chat_id": to_chat_id,
            "from_chat_id": SHOP_CHANNEL,
            "message_id": message_id
        }
    )


@app.route("/", methods=["GET"])
def home():
    return "VYLKA.SHOP bot is running", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True) or {}

    message = update.get("message")

    if not message:
        return "OK", 200

    chat = message.get("chat", {})
    chat_id = chat.get("id")

    if not chat_id:
        return "OK", 200

    text = message.get("text", "")

    # ---------------------------
    # ПОКУПЕЦЬ
    # ---------------------------
    if chat.get("type") == "private":

        # Приклад:
        # https://t.me/vylkashop_orders_bot?start=post_7

        if text.startswith("/start"):

            parts = text.split(maxsplit=1)

            if len(parts) == 2 and parts[1].startswith("post_"):

                try:
                    post_id = int(parts[1].replace("post_", "", 1))
                except ValueError:
                    post_id = None

                if post_id:

                    customer_products[chat_id] = post_id

                    # Показуємо покупцю сам товар
                    copy_product(chat_id, post_id)

                    send_message(
                        chat_id,
                        "👋 Ви обрали цей товар.\n\n"
                        "Напишіть ваше запитання або повідомлення для менеджера."
                    )

                    return "OK", 200

            send_message(
                chat_id,
                "👋 Вітаємо у VYLKA.SHOP!\n\n"
                "Оберіть товар у нашому каналі та натисніть "
                "«Запитати / Замовити»."
            )

            return "OK", 200

        # Звичайне повідомлення покупця
        post_id = customer_products.get(chat_id)

        user = message.get("from", {})
        first_name = user.get("first_name", "Покупець")
        username = user.get("username")

        customer_name = first_name

        if username:
            customer_name += f" (@{username})"

        # Спочатку менеджеру показуємо товар
        if post_id:
            copy_product(MANAGER_CHAT_ID, post_id)

        # Потім повідомлення покупця
        manager_text = (
            f"👤 Покупець: {customer_name}\n"
            f"🆔 ID: {chat_id}\n"
        )

        if post_id:
            manager_text += f"📦 Пост товару: #{post_id}\n"

        manager_text += "\n💬 Повідомлення:\n"

        if text:
            manager_text += text
        else:
            manager_text += "[медіа або інший тип повідомлення]"

        send_message(
            MANAGER_CHAT_ID,
            manager_text,
            {
                "inline_keyboard": [
                    [
                        {
                            "text": "✍️ Відповісти покупцю",
                            "callback_data": f"reply_{chat_id}"
                        }
                    ]
                ]
            }
        )

        return "OK", 200

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
