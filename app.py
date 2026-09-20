import os
import requests
import psycopg2
from flask import Flask, request, jsonify

app = Flask(__name__)


# =========================================================
# НАЛАШТУВАННЯ
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]
MANAGER_CHAT_ID = os.environ["MANAGER_CHAT_ID"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_USER_ID = int(os.environ["ADMIN_USER_ID"])

SHOP_CHANNEL = "@vylkashop"
BOT_USERNAME = "vylkashop_orders_bot"
RENDER_URL = "https://vylkashop-orders-bot.onrender.com"

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )


def init_db():
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id BIGINT PRIMARY KEY,
                    topic_id BIGINT UNIQUE,
                    post_id BIGINT,
                    customer_name TEXT,
                    product_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

        conn.commit()
        print("Database initialized successfully.")

    finally:
        conn.close()


def get_customer(customer_id):
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    customer_id,
                    topic_id,
                    post_id,
                    customer_name,
                    product_sent
                FROM customers
                WHERE customer_id = %s
                """,
                (customer_id,)
            )

            row = cur.fetchone()

            if not row:
                return None

            return {
                "customer_id": row[0],
                "topic_id": row[1],
                "post_id": row[2],
                "customer_name": row[3],
                "product_sent": row[4]
            }

    finally:
        conn.close()


def get_customer_by_topic(topic_id):
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    customer_id,
                    topic_id,
                    post_id,
                    customer_name,
                    product_sent
                FROM customers
                WHERE topic_id = %s
                """,
                (topic_id,)
            )

            row = cur.fetchone()

            if not row:
                return None

            return {
                "customer_id": row[0],
                "topic_id": row[1],
                "post_id": row[2],
                "customer_name": row[3],
                "product_sent": row[4]
            }

    finally:
        conn.close()


def save_selected_product(customer_id, customer_name, post_id):
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customers (
                    customer_id,
                    customer_name,
                    post_id,
                    product_sent
                )
                VALUES (%s, %s, %s, FALSE)

                ON CONFLICT (customer_id)
                DO UPDATE SET
                    customer_name = EXCLUDED.customer_name,
                    post_id = EXCLUDED.post_id,
                    product_sent = FALSE,
                    updated_at = NOW()
                """,
                (
                    customer_id,
                    customer_name,
                    post_id
                )
            )

        conn.commit()

    finally:
        conn.close()


def ensure_customer(customer_id, customer_name):
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customers (
                    customer_id,
                    customer_name
                )
                VALUES (%s, %s)

                ON CONFLICT (customer_id)
                DO UPDATE SET
                    customer_name = EXCLUDED.customer_name,
                    updated_at = NOW()
                """,
                (
                    customer_id,
                    customer_name
                )
            )

        conn.commit()

    finally:
        conn.close()


def save_topic(customer_id, topic_id):
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customers
                SET
                    topic_id = %s,
                    updated_at = NOW()
                WHERE customer_id = %s
                """,
                (
                    topic_id,
                    customer_id
                )
            )

        conn.commit()

    finally:
        conn.close()


def clear_topic(customer_id):
    """
    Видаляємо старий topic_id з Neon,
    якщо гілка Telegram більше не існує.
    """
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customers
                SET
                    topic_id = NULL,
                    product_sent = FALSE,
                    updated_at = NOW()
                WHERE customer_id = %s
                """,
                (customer_id,)
            )

        conn.commit()

    finally:
        conn.close()


def mark_product_sent(customer_id):
    conn = get_db()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE customers
                SET
                    product_sent = TRUE,
                    updated_at = NOW()
                WHERE customer_id = %s
                """,
                (customer_id,)
            )

        conn.commit()

    finally:
        conn.close()


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
    message_thread_id=None,
    reply_markup=None
):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if message_thread_id:
        data["message_thread_id"] = message_thread_id

    if reply_markup:
        data["reply_markup"] = reply_markup

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


def is_thread_not_found(result):
    """
    Перевіряємо, чи Telegram повідомив,
    що гілка більше не існує.
    """
    if result.get("ok"):
        return False

    description = result.get(
        "description",
        ""
    ).lower()

    return "message thread not found" in description


# =========================================================
# ПУБЛІКАЦІЯ ТОВАРУ
# =========================================================

def publish_product(source_chat_id, source_message_id):
    """
    Поточна робоча логіка /publish.
    Її не змінюємо.
    """

    result = copy_message(
        SHOP_CHANNEL,
        source_chat_id,
        source_message_id
    )

    if not result.get("ok"):
        return result

    post_id = result["result"]["message_id"]

    product_link = (
        f"https://t.me/{BOT_USERNAME}"
        f"?start=post_{post_id}"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🛒 Запитати / Замовити",
                    "url": product_link
                }
            ]
        ]
    }

    keyboard_result = telegram(
        "editMessageReplyMarkup",
        {
            "chat_id": SHOP_CHANNEL,
            "message_id": post_id,
            "reply_markup": keyboard
        }
    )

    if not keyboard_result.get("ok"):
        return keyboard_result

    return {
        "ok": True,
        "post_id": post_id,
        "product_link": product_link
    }


# =========================================================
# ГІЛКИ
# =========================================================

def create_new_customer_topic(customer_id, customer_name):
    """
    Завжди створює НОВУ гілку.
    """

    topic_name = f"👤 {customer_name}"
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
            "Не вдалося створити нову гілку:",
            result
        )
        return None

    topic_id = result[
        "result"
    ][
        "message_thread_id"
    ]

    save_topic(
        customer_id,
        topic_id
    )

    print(
        f"Створено нову гілку "
        f"{topic_id} для покупця {customer_id}"
    )

    return topic_id


def create_customer_topic(customer_id, customer_name):
    """
    Якщо в Neon вже є topic_id — використовуємо його.
    Якщо немає — створюємо нову гілку.
    """

    customer = get_customer(
        customer_id
    )

    if customer and customer["topic_id"]:
        return customer["topic_id"]

    return create_new_customer_topic(
        customer_id,
        customer_name
    )


def send_customer_header_and_product(
    customer_id,
    customer_name,
    post_id,
    topic_id
):
    """
    Відправляємо в нову гілку інформацію
    про покупця та вибраний товар.
    """

    info = (
        "🛍 НОВЕ ЗВЕРНЕННЯ\n\n"
        f"👤 Покупець: {customer_name}\n"
        f"🆔 Telegram ID: {customer_id}"
    )

    info_result = send_message(
        MANAGER_CHAT_ID,
        info,
        topic_id
    )

    if not info_result.get("ok"):
        return info_result

    if post_id:
        product_result = copy_product(
            MANAGER_CHAT_ID,
            post_id,
            topic_id
        )

        if not product_result.get("ok"):
            return product_result

    mark_product_sent(
        customer_id
    )

    return {
        "ok": True
    }


def recreate_customer_topic(
    customer_id,
    customer_name,
    post_id
):
    """
    Стара гілка видалена:
    очищаємо topic_id,
    створюємо нову гілку,
    повторно надсилаємо інформацію і товар.
    """

    print(
        f"Гілка покупця {customer_id} "
        "більше не існує. Створюємо нову."
    )

    clear_topic(
        customer_id
    )

    new_topic_id = create_new_customer_topic(
        customer_id,
        customer_name
    )

    if not new_topic_id:
        return None

    header_result = send_customer_header_and_product(
        customer_id,
        customer_name,
        post_id,
        new_topic_id
    )

    if not header_result.get("ok"):
        print(
            "Не вдалося заповнити нову гілку:",
            header_result
        )
        return None

    return new_topic_id


# =========================================================
# СТАН /publish
# =========================================================

admin_publish_mode = set()


# =========================================================
# ROUTES
# =========================================================

@app.route("/", methods=["GET"])
def home():
    return "VYLKA.SHOP bot is running", 200


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

    update = request.get_json(
        silent=True
    ) or {}

    print(
        "UPDATE:",
        update
    )

    message = update.get(
        "message"
    )

    if not message:
        return "OK", 200

    sender = message.get(
        "from",
        {}
    )

    # Не обробляємо повідомлення самого бота
    if sender.get("is_bot"):
        return "OK", 200

    chat = message.get(
        "chat",
        {}
    )

    chat_id = chat.get("id")
    chat_type = chat.get("type")

    if not chat_id:
        return "OK", 200

    text = message.get(
        "text",
        ""
    )


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
    # ПРИВАТНИЙ ЧАТ
    # =====================================================

    if chat_type == "private":

        customer_id = chat_id

        first_name = sender.get(
            "first_name",
            "Покупець"
        )

        username = sender.get(
            "username"
        )

        customer_name = first_name

        if username:
            customer_name += (
                f" @{username}"
            )


        # =================================================
        # /publish — ТІЛЬКИ АДМІН
        # =================================================

        if customer_id == ADMIN_USER_ID:

            if text == "/cancel":

                admin_publish_mode.discard(
                    customer_id
                )

                send_message(
                    customer_id,
                    "❌ Публікацію скасовано."
                )

                return "OK", 200


            if text == "/publish":

                admin_publish_mode.add(
                    customer_id
                )

                send_message(
                    customer_id,
                    "📦 Режим публікації товару.\n\n"
                    "Тепер надішліть ОДНЕ повідомлення "
                    "з товаром.\n\n"
                    "Це може бути:\n"
                    "• фото + опис;\n"
                    "• відео + опис;\n"
                    "• або текстовий пост.\n\n"
                    "Бот опублікує його у VYLKA.SHOP "
                    "і автоматично додасть кнопку "
                    "«🛒 Запитати / Замовити».\n\n"
                    "Для скасування: /cancel"
                )

                return "OK", 200


            if customer_id in admin_publish_mode:

                admin_publish_mode.discard(
                    customer_id
                )

                result = publish_product(
                    customer_id,
                    message["message_id"]
                )

                if result.get("ok"):

                    post_id = result[
                        "post_id"
                    ]

                    send_message(
                        customer_id,
                        "✅ Товар успішно опубліковано!\n\n"
                        f"Номер поста: {post_id}\n"
                        "Кнопку «🛒 Запитати / Замовити» "
                        "додано автоматично."
                    )

                else:

                    error_text = result.get(
                        "description",
                        result.get(
                            "error",
                            "Невідома помилка"
                        )
                    )

                    send_message(
                        customer_id,
                        "⚠️ Не вдалося опублікувати товар.\n\n"
                        f"Помилка: {error_text}\n\n"
                        "Спробуйте /publish ще раз."
                    )

                return "OK", 200


        # =================================================
        # /start
        # =================================================

        if text.startswith("/start"):

            parts = text.split(
                maxsplit=1
            )

            if len(parts) == 2:

                parameter = parts[1]

                if parameter.startswith(
                    "post_"
                ):

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

                        save_selected_product(
                            customer_id,
                            customer_name,
                            post_id
                        )

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

        ensure_customer(
            customer_id,
            customer_name
        )

        customer = get_customer(
            customer_id
        )

        post_id = (
            customer["post_id"]
            if customer
            else None
        )

        topic_id = create_customer_topic(
            customer_id,
            customer_name
        )

        if not topic_id:

            send_message(
                customer_id,
                "⚠️ Не вдалося передати повідомлення "
                "менеджеру.\n\n"
                "Спробуйте ще раз трохи пізніше."
            )

            return "OK", 200


        # =================================================
        # ЯКЩО ТОВАР ЩЕ НЕ ПОКАЗАНИЙ МЕНЕДЖЕРУ
        # =================================================

        customer = get_customer(
            customer_id
        )

        if not customer["product_sent"]:

            header_result = (
                send_customer_header_and_product(
                    customer_id,
                    customer_name,
                    post_id,
                    topic_id
                )
            )

            # Якщо саме тут виявили,
            # що стара гілка вже видалена
            if is_thread_not_found(
                header_result
            ):

                topic_id = recreate_customer_topic(
                    customer_id,
                    customer_name,
                    post_id
                )

                if not topic_id:

                    send_message(
                        customer_id,
                        "⚠️ Не вдалося відновити чат "
                        "із менеджером.\n\n"
                        "Спробуйте ще раз трохи пізніше."
                    )

                    return "OK", 200

            elif not header_result.get("ok"):

                send_message(
                    customer_id,
                    "⚠️ Не вдалося передати товар "
                    "менеджеру.\n\n"
                    "Спробуйте ще раз трохи пізніше."
                )

                return "OK", 200


        # =================================================
        # КОПІЮЄМО ПОВІДОМЛЕННЯ ПОКУПЦЯ
        # =================================================

        copy_result = copy_message(
            MANAGER_CHAT_ID,
            customer_id,
            message["message_id"],
            topic_id
        )


        # =================================================
        # СТАРА ГІЛКА ВИДАЛЕНА
        # =================================================

        if is_thread_not_found(
            copy_result
        ):

            topic_id = recreate_customer_topic(
                customer_id,
                customer_name,
                post_id
            )

            if not topic_id:

                send_message(
                    customer_id,
                    "⚠️ Не вдалося відновити чат "
                    "із менеджером.\n\n"
                    "Спробуйте ще раз трохи пізніше."
                )

                return "OK", 200


            # Повторюємо відправлення повідомлення
            copy_result = copy_message(
                MANAGER_CHAT_ID,
                customer_id,
                message["message_id"],
                topic_id
            )


        # =================================================
        # FALLBACK ДЛЯ ТЕКСТУ
        # =================================================

        if not copy_result.get("ok") and text:

            fallback_result = send_message(
                MANAGER_CHAT_ID,
                f"💬 {text}",
                topic_id
            )

            if fallback_result.get("ok"):
                copy_result = fallback_result


        # =================================================
        # ПІДТВЕРДЖЕННЯ ТІЛЬКИ ПІСЛЯ УСПІХУ
        # =================================================

        if copy_result.get("ok"):

            send_message(
                customer_id,
                "✅ Повідомлення передано менеджеру."
            )

        else:

            print(
                "Не вдалося доставити повідомлення:",
                copy_result
            )

            send_message(
                customer_id,
                "⚠️ Повідомлення не вдалося "
                "передати менеджеру.\n\n"
                "Спробуйте ще раз трохи пізніше."
            )

        return "OK", 200


    # =====================================================
    # ГРУПА МЕНЕДЖЕРІВ → ПОКУПЕЦЬ
    # =====================================================

    if str(chat_id) == str(
        MANAGER_CHAT_ID
    ):

        topic_id = message.get(
            "message_thread_id"
        )

        if not topic_id:
            return "OK", 200

        customer = get_customer_by_topic(
            topic_id
        )

        if not customer:

            print(
                f"Для topic_id={topic_id} "
                "покупця в базі не знайдено."
            )

            return "OK", 200

        customer_id = customer[
            "customer_id"
        ]

        result = copy_message(
            customer_id,
            MANAGER_CHAT_ID,
            message["message_id"]
        )

        if not result.get("ok") and text:

            send_message(
                customer_id,
                f"💬 Менеджер VYLKA.SHOP:\n\n{text}"
            )

        return "OK", 200


    return "OK", 200


# =========================================================
# DATABASE STARTUP
# =========================================================

try:
    init_db()

except Exception as error:

    print(
        "DATABASE INITIALIZATION ERROR:",
        error
    )


# =========================================================
# LOCAL START
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
