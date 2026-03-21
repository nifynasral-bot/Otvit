import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import time
import json
import os
import threading

# Токен из переменных окружения Railway
TOKEN = os.getenv("VK_TOKEN", "vk1.a.mqK7Hhet4GaA6NxNlMbnc0YP2ZHC_18aTaVabwrFzfC6yBFQ4xwA3vdWqHtsMwCIg7Uk6CH934HgBKxtpHF1qjn8Zpk1vNdsWKSlPSCQPvp1vz-lELEAcm85wBEtr9iOmF-zUKRPK_0Epw_Pg0a6eCgOCaYwp_Wp3Vd0VbgaxRNxRg8oV90PQgY-C6vYdJTELxIL2P0fy17-KoMWadkCfQ")

# Твой VK ID (владелец бота)
OWNER_ID = 795602888

# Файлы данных
DUPLICATED_FILE = "duplicated_chats.json"
BANNED_FILE = "banned_users.json"
SETTINGS_FILE = "settings.json"

# Хранилище в памяти
greeted_users = set()
all_writers = set()  # все кто писал


# ==================== РАБОТА С ФАЙЛАМИ ====================

def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default.copy()


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_duplicated():
    return load_json(DUPLICATED_FILE, {"tickets": [], "next_id": 1})


def save_duplicated(data):
    save_json(DUPLICATED_FILE, data)


def load_banned():
    return load_json(BANNED_FILE, {"users": []})


def save_banned(data):
    save_json(BANNED_FILE, data)


def load_settings():
    return load_json(SETTINGS_FILE, {
        "autoresponder_enabled": True,
        "status": "default",
        "custom_reply": ""
    })


def save_settings(data):
    save_json(SETTINGS_FILE, data)


# ==================== УТИЛИТЫ ====================

def get_user_name(vk, user_id):
    try:
        info = vk.users.get(user_ids=user_id)
        if info:
            return f"{info[0]['first_name']} {info[0]['last_name']}"
    except Exception:
        pass
    return f"ID {user_id}"


def send_message(vk, user_id, message):
    for attempt in range(3):
        try:
            vk.messages.send(
                user_id=user_id,
                message=message,
                random_id=int(time.time() * 1000000)
            )
            print(f"[OK] -> {user_id}", flush=True)
            return True
        except vk_api.exceptions.ApiError as e:
            print(f"[API] {e}", flush=True)
            return False
        except Exception as e:
            print(f"[СЕТЬ] {attempt + 1}/3: {e}", flush=True)
            time.sleep(3)
    return False


def send_chat_message(vk, peer_id, message):
    for attempt in range(3):
        try:
            vk.messages.send(
                peer_id=peer_id,
                message=message,
                random_id=int(time.time() * 1000000)
            )
            return True
        except vk_api.exceptions.ApiError as e:
            print(f"[API чат] {e}", flush=True)
            return False
        except Exception as e:
            print(f"[СЕТЬ чат] {attempt + 1}/3: {e}", flush=True)
            time.sleep(3)
    return False


def is_night():
    hour = int(time.strftime("%H"))
    return hour >= 23 or hour < 7


def get_auto_reply(settings):
    if settings.get("custom_reply"):
        return settings["custom_reply"]

    if settings.get("status") == "busy":
        return (
            "🔴 Сейчас я занят и не могу ответить.\n\n"
            "📌 Спустя пару часов пиши: /продублировать — и ожидай ответа!"
        )

    if is_night():
        return (
            "🌙 Привет! Сейчас ночь, я сплю.\n"
            "Отвечу утром!\n\n"
            "📌 Чтобы не потеряться, напиши: /продублировать"
        )

    return (
        "Привет! Спасибо за обращение, ожидай ответа!\n\n"
        "🕐 Появляюсь в сети несколько раз в час! Жди, "
        "но ты можешь затеряться среди других чатов.\n\n"
        "📌 Спустя пару часов пиши: /продублировать — и ожидай ответа!"
    )


# ==================== АВТО-ПРИНЯТИЕ ЗАЯВОК ====================

def auto_accept_friends(vk):
    """Поток для автоматического принятия заявок в друзья"""
    print("[i] Авто-принятие заявок запущено", flush=True)
    while True:
        try:
            requests_list = vk.friends.getRequests(need_viewed=1)
            friend_ids = requests_list.get("items", [])

            for uid in friend_ids:
                try:
                    # Проверяем: можно ли добавить или нужно подписаться
                    vk.friends.add(user_id=uid)
                    name = get_user_name(vk, uid)
                    print(f"[+] Принята заявка: {name} ({uid})", flush=True)
                except vk_api.exceptions.ApiError as e:
                    if "cannot add this user" in str(e).lower():
                        print(f"[~] Нельзя принять {uid} (подписка)", flush=True)
                    else:
                        print(f"[~] Заявка {uid}: {e}", flush=True)

            time.sleep(3)

        except Exception as e:
            print(f"[!] Ошибка заявок: {e}", flush=True)
            time.sleep(10)


# ==================== РАССЫЛКА ====================

def get_all_dialogs(vk):
    """Получает всех пользователей из диалогов"""
    all_users = set()
    offset = 0

    while True:
        try:
            result = vk.messages.getConversations(
                offset=offset,
                count=200,
                filter="all"
            )

            items = result.get("items", [])
            if not items:
                break

            for item in items:
                peer = item.get("conversation", {}).get("peer", {})
                if peer.get("type") == "user":
                    user_id = peer.get("id")
                    if user_id and user_id != OWNER_ID:
                        all_users.add(user_id)

            offset += 200

            if offset >= result.get("count", 0):
                break

            time.sleep(0.5)

        except Exception as e:
            print(f"[!] Ошибка диалогов: {e}", flush=True)
            break

    return all_users


def do_broadcast(vk, text, user_id):
    """Выполняет рассылку"""
    send_message(vk, user_id, "⏳ Собираю список диалогов...")

    users = get_all_dialogs(vk)
    total = len(users)
    sent = 0
    failed = 0

    send_message(vk, user_id, f"📤 Начинаю рассылку по {total} пользователям...")

    for uid in users:
        try:
            vk.messages.send(
                user_id=uid,
                message=text,
                random_id=int(time.time() * 1000000)
            )
            sent += 1
        except Exception:
            failed += 1

        time.sleep(1)  # Задержка от бана

        if (sent + failed) % 50 == 0:
            send_message(vk, user_id,
                         f"📤 Прогресс: {sent + failed}/{total} "
                         f"(отправлено: {sent}, ошибок: {failed})")

    send_message(vk, user_id,
                 f"✅ Рассылка завершена!\n\n"
                 f"📊 Всего: {total}\n"
                 f"✉️ Отправлено: {sent}\n"
                 f"❌ Ошибок: {failed}")


# ==================== ОБРАБОТКА БЕСЕДЫ ====================

def process_chat_message(vk, event):
    """Обработка сообщений в беседах — ответ на упоминание"""
    text = event.text if event.text else ""

    # Проверяем упоминание @ovcin
    if "@ovcin" in text.lower() or "[id795602888|" in text.lower():
        peer_id = event.peer_id
        send_chat_message(vk, peer_id,
                          "Я пока что не на месте, но скоро буду, ожидай")
        print(f"[i] Ответил на упоминание в чате {peer_id}", flush=True)


# ==================== ОБРАБОТКА ЛС ====================

def process_message(vk, event, duplicated_data, banned_data, settings):
    user_id = event.user_id
    text = event.text.strip() if event.text else ""
    text_lower = text.lower()
    user_name = get_user_name(vk, user_id)

    print(f"[<] {user_name} ({user_id}): {text}", flush=True)

    # Запоминаем что человек писал
    all_writers.add(user_id)

    # Проверяем бан
    if user_id in banned_data["users"] and user_id != OWNER_ID:
        print(f"[i] Заблокированный {user_name}, игнор", flush=True)
        return

    # ==================== КОМАНДЫ ДЛЯ ВСЕХ ====================

    # /помощь
    if text_lower in ["/помощь", "/help", "/команды"]:
        help_text = (
            "📋 Доступные команды:\n\n"
            "📌 /продублировать — продублировать обращение чтобы не потерялось\n"
            "❓ /помощь — показать этот список\n\n"
            "Просто напиши свой вопрос и жди ответа!"
        )
        send_message(vk, user_id, help_text)
        return

    # /продублировать
    if text_lower in ["/продублировать", "/дублировать"]:
        # Проверяем нет ли уже открытого тикета
        existing = None
        for ticket in duplicated_data["tickets"]:
            if ticket["user_id"] == user_id and ticket["status"] == "open":
                existing = ticket
                break

        if existing:
            send_message(vk, user_id,
                         f"ℹ️ У тебя уже есть обращение #{existing['id']}.\n"
                         f"Ожидай ответа!")
        else:
            ticket_id = duplicated_data["next_id"]
            duplicated_data["next_id"] = ticket_id + 1

            ticket = {
                "id": ticket_id,
                "user_id": user_id,
                "name": user_name,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "open"  # open / taken / declined / banned
            }
            duplicated_data["tickets"].append(ticket)
            save_duplicated(duplicated_data)

            send_message(vk, user_id,
                         f"✅ Твоё обращение #{ticket_id} продублировано!\n"
                         f"Я обязательно отвечу, как только появлюсь в сети.")

            # Уведомление владельцу
            send_message(vk, OWNER_ID,
                         f"🔔 Новое обращение #{ticket_id}\n"
                         f"От: {user_name} (vk.com/id{user_id})\n"
                         f"Время: {ticket['time']}")

            print(f"[+] Тикет #{ticket_id} от {user_name}", flush=True)
        return

    # ==================== КОМАНДЫ ВЛАДЕЛЬЦА ====================

    if user_id != OWNER_ID:
        # Автоответ для обычных пользователей
        if settings.get("autoresponder_enabled", True):
            if user_id not in greeted_users:
                greeted_users.add(user_id)
                reply = get_auto_reply(settings)
                send_message(vk, user_id, reply)
        return

    # === Далее только команды владельца ===

    # /помощьадмин
    if text_lower in ["/помощьадмин", "/helpadmin", "/админ"]:
        admin_help = (
            "👑 Команды владельца:\n\n"
            "📋 Тикеты:\n"
            "  /статус — список обращений\n"
            "  /взяться (id) — взяться за ответ\n"
            "  /отклонить (id) — отклонить обращение\n"
            "  /бан (id) — забанить пользователя\n"
            "  /очистить — очистить все обращения\n\n"
            "📤 Рассылка:\n"
            "  /рассылка текст — рассылка всем из диалогов\n\n"
            "⚙️ Настройки:\n"
            "  /занят — статус «занят»\n"
            "  /свободен — обычный статус\n"
            "  /стоп — выключить автоответчик\n"
            "  /старт — включить автоответчик\n"
            "  /автоответ текст — свой текст автоответа\n"
            "  /сброс — сбросить текст автоответа\n\n"
            "👥 Пользователи:\n"
            "  /разбан (user_id) — разбанить\n"
            "  /баны — список забаненных"
        )
        send_message(vk, user_id, admin_help)
        return

    # /статус
    if text_lower == "/статус":
        open_tickets = [t for t in duplicated_data["tickets"] if t["status"] == "open"]
        taken_tickets = [t for t in duplicated_data["tickets"] if t["status"] == "taken"]

        if not open_tickets and not taken_tickets:
            send_message(vk, user_id, "📋 Нет активных обращений.")
            return

        msg = ""

        if open_tickets:
            msg += "📋 Открытые обращения:\n\n"
            for t in open_tickets:
                msg += (f"🔹 #{t['id']} — {t['name']} "
                        f"(vk.com/id{t['user_id']})\n"
                        f"   📅 {t['time']}\n\n")

        if taken_tickets:
            msg += "🔧 В работе:\n\n"
            for t in taken_tickets:
                msg += (f"🔸 #{t['id']} — {t['name']} "
                        f"(vk.com/id{t['user_id']})\n"
                        f"   📅 {t['time']}\n\n")

        send_message(vk, user_id, msg)
        return

    # /взяться (id)
    if text_lower.startswith("/взяться"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Укажи ID: /взяться 1")
            return

        try:
            ticket_id = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID должен быть числом")
            return

        ticket = None
        for t in duplicated_data["tickets"]:
            if t["id"] == ticket_id:
                ticket = t
                break

        if not ticket:
            send_message(vk, user_id, f"❌ Тикет #{ticket_id} не найден")
            return

        if ticket["status"] != "open":
            send_message(vk, user_id,
                         f"❌ Тикет #{ticket_id} уже обработан "
                         f"(статус: {ticket['status']})")
            return

        ticket["status"] = "taken"
        save_duplicated(duplicated_data)

        # Уведомляем пользователя
        send_message(vk, ticket["user_id"],
                     "✅ @ovcin взялся за ваш вопрос, "
                     "ожидайте ответа в течение 5 минут.")

        send_message(vk, user_id,
                     f"✅ Ты взялся за тикет #{ticket_id} "
                     f"({ticket['name']})")
        return

    # /отклонить (id)
    if text_lower.startswith("/отклонить"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Укажи ID: /отклонить 1")
            return

        try:
            ticket_id = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID должен быть числом")
            return

        ticket = None
        for t in duplicated_data["tickets"]:
            if t["id"] == ticket_id:
                ticket = t
                break

        if not ticket:
            send_message(vk, user_id, f"❌ Тикет #{ticket_id} не найден")
            return

        ticket["status"] = "declined"
        save_duplicated(duplicated_data)

        send_message(vk, ticket["user_id"],
                     "❌ Ваше обращение было отклонено.")

        send_message(vk, user_id,
                     f"✅ Тикет #{ticket_id} отклонён ({ticket['name']})")
        return

    # /бан (id тикета)
    if text_lower.startswith("/бан"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Укажи ID тикета: /бан 1")
            return

        try:
            ticket_id = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID должен быть числом")
            return

        ticket = None
        for t in duplicated_data["tickets"]:
            if t["id"] == ticket_id:
                ticket = t
                break

        if not ticket:
            send_message(vk, user_id, f"❌ Тикет #{ticket_id} не найден")
            return

        ban_user_id = ticket["user_id"]
        ticket["status"] = "banned"
        save_duplicated(duplicated_data)

        # Добавляем в бан-лист
        if ban_user_id not in banned_data["users"]:
            banned_data["users"].append(ban_user_id)
            save_banned(banned_data)

        # Блокируем в ВК
        try:
            vk.account.ban(owner_id=ban_user_id)
        except Exception as e:
            print(f"[!] Ошибка блокировки: {e}", flush=True)

        # Уведомляем пользователя
        send_message(vk, ban_user_id,
                     "⛔ Пользователь заблокировал вас.")

        send_message(vk, user_id,
                     f"⛔ {ticket['name']} (id{ban_user_id}) "
                     f"заблокирован, тикет #{ticket_id} закрыт")
        return

    # /разбан (user_id)
    if text_lower.startswith("/разбан"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Укажи user_id: /разбан 123456")
            return

        try:
            unban_id = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID должен быть числом")
            return

        if unban_id in banned_data["users"]:
            banned_data["users"].remove(unban_id)
            save_banned(banned_data)

        try:
            vk.account.unban(owner_id=unban_id)
        except Exception:
            pass

        name = get_user_name(vk, unban_id)
        send_message(vk, user_id, f"✅ {name} (id{unban_id}) разблокирован")
        return

    # /баны
    if text_lower == "/баны":
        if not banned_data["users"]:
            send_message(vk, user_id, "📋 Список забаненных пуст.")
            return

        msg = "⛔ Забаненные:\n\n"
        for i, uid in enumerate(banned_data["users"], 1):
            name = get_user_name(vk, uid)
            msg += f"{i}. {name} (vk.com/id{uid})\n"

        send_message(vk, user_id, msg)
        return

    # /очистить
    if text_lower == "/очистить":
        duplicated_data["tickets"] = []
        duplicated_data["next_id"] = 1
        save_duplicated(duplicated_data)
        send_message(vk, user_id, "🗑 Все обращения очищены.")
        return

    # /рассылка текст
    if text_lower.startswith("/рассылка"):
        broadcast_text = text[len("/рассылка"):].strip()
        if not broadcast_text:
            send_message(vk, user_id,
                         "❌ Укажи текст: /рассылка Привет всем!")
            return

        # Запускаем в отдельном потоке чтобы не блокировать бота
        thread = threading.Thread(
            target=do_broadcast,
            args=(vk, broadcast_text, user_id),
            daemon=True
        )
        thread.start()
        return

    # /занят
    if text_lower == "/занят":
        settings["status"] = "busy"
        settings["custom_reply"] = ""
        save_settings(settings)
        send_message(vk, user_id,
                     "🔴 Статус: занят. Автоответ изменён.")
        return

    # /свободен
    if text_lower == "/свободен":
        settings["status"] = "default"
        settings["custom_reply"] = ""
        save_settings(settings)
        send_message(vk, user_id,
                     "🟢 Статус: свободен. Автоответ стандартный.")
        return

    # /стоп
    if text_lower == "/стоп":
        settings["autoresponder_enabled"] = False
        save_settings(settings)
        send_message(vk, user_id, "⏸ Автоответчик выключен.")
        return

    # /старт
    if text_lower == "/старт":
        settings["autoresponder_enabled"] = True
        save_settings(settings)
        send_message(vk, user_id, "▶️ Автоответчик включен.")
        return

    # /автоответ текст
    if text_lower.startswith("/автоответ"):
        custom = text[len("/автоответ"):].strip()
        if not custom:
            send_message(vk, user_id,
                         "❌ Укажи текст: /автоответ Я сейчас занят...")
            return

        settings["custom_reply"] = custom
        save_settings(settings)
        send_message(vk, user_id,
                     f"✅ Автоответ установлен:\n\n{custom}")
        return

    # /сброс
    if text_lower == "/сброс":
        settings["custom_reply"] = ""
        settings["status"] = "default"
        save_settings(settings)
        send_message(vk, user_id,
                     "✅ Автоответ сброшен на стандартный.")
        return


# ==================== ПОДКЛЮЧЕНИЕ ====================

def connect_vk():
    while True:
        try:
            print("[...] Подключаюсь к ВК...", flush=True)
            vk_session = vk_api.VkApi(token=TOKEN)
            vk = vk_session.get_api()
            info = vk.account.getProfileInfo()
            print(f"[OK] Вошли как: {info['first_name']} "
                  f"{info['last_name']}", flush=True)
            return vk_session, vk
        except Exception as e:
            print(f"[ОШИБКА] {e}", flush=True)
            print("[i] Повтор через 10 сек...", flush=True)
            time.sleep(10)


# ==================== ГЛАВНЫЙ ЦИКЛ ====================

def main():
    print("=" * 50, flush=True)
    print("    VK Автоответчик v2.0 (Railway)", flush=True)
    print("=" * 50, flush=True)

    if not TOKEN or len(TOKEN) < 20:
        print("\n[!] ТОКЕН НЕ НАЙДЕН!", flush=True)
        print("Добавь VK_TOKEN в переменные Railway", flush=True)
        return

    vk_session, vk = connect_vk()

    # Загружаем данные
    duplicated_data = load_duplicated()
    banned_data = load_banned()
    settings = load_settings()

    # Запускаем авто-принятие заявок в друзья
    friend_thread = threading.Thread(
        target=auto_accept_friends,
        args=(vk,),
        daemon=True
    )
    friend_thread.start()

    print(f"\n[i] Владелец: id{OWNER_ID}", flush=True)
    print(f"[i] Автоответчик: "
          f"{'ВКЛ' if settings.get('autoresponder_enabled', True) else 'ВЫКЛ'}",
          flush=True)
    print(f"[i] Статус: {settings.get('status', 'default')}", flush=True)
    print(f"[i] Тикетов: {len(duplicated_data.get('tickets', []))}", flush=True)
    print(f"[i] Банов: {len(banned_data.get('users', []))}", flush=True)
    print("\n[>] Бот слушает...", flush=True)
    print("-" * 50, flush=True)

    while True:
        try:
            longpoll = VkLongPoll(vk_session)

            for event in longpoll.listen():
                if event.type != VkEventType.MESSAGE_NEW:
                    continue
                if event.from_me:
                    continue

                # Сообщение в беседе
                if event.from_chat:
                    try:
                        process_chat_message(vk, event)
                    except Exception as e:
                        print(f"[!] Ошибка чата: {e}", flush=True)
                    continue

                # Личное сообщение
                try:
                    process_message(vk, event,
                                    duplicated_data,
                                    banned_data,
                                    settings)
                except Exception as e:
                    print(f"[!] Ошибка ЛС: {e}", flush=True)

        except KeyboardInterrupt:
            print("\n[X] Бот остановлен", flush=True)
            return

        except Exception as e:
            print(f"\n[!] Потеря соединения: {e}", flush=True)
            print("[i] Переподключение через 5 сек...", flush=True)
            time.sleep(5)

            try:
                vk_session, vk = connect_vk()

                # Перезапускаем поток заявок
                friend_thread = threading.Thread(
                    target=auto_accept_friends,
                    args=(vk,),
                    daemon=True
                )
                friend_thread.start()

                print("[OK] Переподключился!", flush=True)
            except Exception:
                pass


if __name__ == "__main__":
    main()
