import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import time
import json
import os
import threading

TOKEN = os.getenv("VK_TOKEN", "k1.a.mqK7Hhet4GaA6NxNlMbnc0YP2ZHC_18aTaVabwrFzfC6yBFQ4xwA3vdWqHtsMwCIg7Uk6CH934HgBKxtpHF1qjn8Zpk1vNdsWKSlPSCQPvp1vz-lELEAcm85wBEtr9iOmF-zUKRPK_0Epw_Pg0a6eCgOCaYwp_Wp3Vd0VbgaxRNxRg8oV90PQgY-C6vYdJTELxIL2P0fy17-KoMWadkCfQ")
OWNER_ID = 795602888

DUPLICATED_FILE = "duplicated_chats.json"
BANNED_FILE = "banned_users.json"
SETTINGS_FILE = "settings.json"

greeted_users = set()


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
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            random_id=int(time.time() * 1000000)
        )
        return True
    except Exception as e:
        print(f"[API чат] {e}", flush=True)
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


def auto_accept_friends(vk):
    already_processed = set()

    while True:
        try:
            result = vk.friends.getRequests(out=0, count=1000, need_viewed=0)
            new_ids = result.get("items", [])

            for uid in new_ids:
                if uid in already_processed:
                    continue

                try:
                    response = vk.friends.add(user_id=uid)
                    if response == 1:
                        name = get_user_name(vk, uid)
                        print(f"[+] Принята заявка: {name} ({uid})", flush=True)
                    already_processed.add(uid)
                except vk_api.exceptions.ApiError:
                    already_processed.add(uid)

        except Exception:
            pass

        time.sleep(30)


def get_all_dialogs(vk):
    all_users = set()
    offset = 0

    while True:
        try:
            result = vk.messages.getConversations(
                offset=offset, count=200, filter="all"
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
    send_message(vk, user_id, "⏳ Собираю список диалогов...")
    users = get_all_dialogs(vk)
    total = len(users)
    sent = 0
    failed = 0

    send_message(vk, user_id, f"📤 Рассылка по {total} пользователям...")

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

        time.sleep(1)

        if (sent + failed) % 50 == 0:
            send_message(vk, user_id,
                         f"📤 {sent + failed}/{total} "
                         f"(ok: {sent}, fail: {failed})")

    send_message(vk, user_id,
                 f"✅ Рассылка завершена!\n\n"
                 f"📊 Всего: {total}\n"
                 f"✉️ Отправлено: {sent}\n"
                 f"❌ Ошибок: {failed}")


def process_chat_message(vk, event):
    text = event.text.lower() if event.text else ""

    if "@ovcin" in text or "[id795602888|" in text:
        send_chat_message(vk, event.peer_id,
                          "Я пока что не на месте, но скоро буду, ожидай")
        print(f"[i] Упоминание в чате {event.peer_id}", flush=True)


def process_message(vk, event, duplicated_data, banned_data, settings):
    user_id = event.user_id
    text = event.text.strip() if event.text else ""
    text_lower = text.lower()
    user_name = get_user_name(vk, user_id)

    print(f"[<] {user_name} ({user_id}): {text}", flush=True)

    if user_id in banned_data["users"] and user_id != OWNER_ID:
        return

    # === КОМАНДЫ ДЛЯ ВСЕХ ===

    if text_lower in ["/помощь", "/help", "/команды"]:
        send_message(vk, user_id,
                     "📋 Команды:\n\n"
                     "📌 /продублировать — продублировать обращение\n"
                     "❓ /помощь — этот список\n\n"
                     "Просто напиши вопрос и жди ответа!")
        return

    if text_lower in ["/продублировать", "/дублировать"]:
        existing = None
        for t in duplicated_data["tickets"]:
            if t["user_id"] == user_id and t["status"] == "open":
                existing = t
                break

        if existing:
            send_message(vk, user_id,
                         f"ℹ️ У тебя уже есть обращение #{existing['id']}.\n"
                         f"Ожидай ответа!")
        else:
            tid = duplicated_data["next_id"]
            duplicated_data["next_id"] = tid + 1

            ticket = {
                "id": tid,
                "user_id": user_id,
                "name": user_name,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "open"
            }
            duplicated_data["tickets"].append(ticket)
            save_duplicated(duplicated_data)

            send_message(vk, user_id,
                         f"✅ Обращение #{tid} создано!\n"
                         f"Я отвечу, как только появлюсь в сети.")

            send_message(vk, OWNER_ID,
                         f"🔔 Новый тикет #{tid}\n"
                         f"От: {user_name} (vk.com/id{user_id})\n"
                         f"Время: {ticket['time']}")
        return

    # === КОМАНДЫ ТОЛЬКО ВЛАДЕЛЬЦА ===

    if user_id != OWNER_ID:
        if settings.get("autoresponder_enabled", True):
            if user_id not in greeted_users:
                greeted_users.add(user_id)
                send_message(vk, user_id, get_auto_reply(settings))
        return

    if text_lower in ["/помощьадмин", "/админ"]:
        send_message(vk, user_id,
                     "👑 Админ-команды:\n\n"
                     "📋 Тикеты:\n"
                     "  /статус — открытые обращения\n"
                     "  /взяться 1 — взяться за тикет\n"
                     "  /отклонить 1 — отклонить\n"
                     "  /бан 1 — забанить автора тикета\n"
                     "  /очистить — удалить все тикеты\n\n"
                     "📤 Рассылка:\n"
                     "  /рассылка текст\n\n"
                     "⚙️ Настройки:\n"
                     "  /занят — статус занят\n"
                     "  /свободен — обычный статус\n"
                     "  /стоп — выключить автоответчик\n"
                     "  /старт — включить автоответчик\n"
                     "  /автоответ текст — свой автоответ\n"
                     "  /сброс — сбросить автоответ\n\n"
                     "👥 Баны:\n"
                     "  /разбан user_id\n"
                     "  /баны — список")
        return

    if text_lower == "/статус":
        open_t = [t for t in duplicated_data["tickets"] if t["status"] == "open"]
        taken_t = [t for t in duplicated_data["tickets"] if t["status"] == "taken"]

        if not open_t and not taken_t:
            send_message(vk, user_id, "📋 Нет активных обращений.")
            return

        msg = ""
        if open_t:
            msg += "📋 Открытые:\n\n"
            for t in open_t:
                msg += (f"🔹 #{t['id']} — {t['name']} "
                        f"(vk.com/id{t['user_id']}) — {t['time']}\n")
            msg += "\n"

        if taken_t:
            msg += "🔧 В работе:\n\n"
            for t in taken_t:
                msg += (f"🔸 #{t['id']} — {t['name']} "
                        f"(vk.com/id{t['user_id']}) — {t['time']}\n")

        send_message(vk, user_id, msg)
        return

    if text_lower.startswith("/взяться"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Формат: /взяться 1")
            return
        try:
            tid = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID — число")
            return

        ticket = next((t for t in duplicated_data["tickets"] if t["id"] == tid), None)
        if not ticket:
            send_message(vk, user_id, f"❌ Тикет #{tid} не найден")
            return
        if ticket["status"] != "open":
            send_message(vk, user_id, f"❌ Тикет #{tid} уже обработан")
            return

        ticket["status"] = "taken"
        save_duplicated(duplicated_data)

        send_message(vk, ticket["user_id"],
                     "✅ @ovcin взялся за ваш вопрос, "
                     "ожидайте ответа в течение 5 минут.")
        send_message(vk, user_id,
                     f"✅ Взялся за #{tid} ({ticket['name']})")
        return

    if text_lower.startswith("/отклонить"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Формат: /отклонить 1")
            return
        try:
            tid = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID — число")
            return

        ticket = next((t for t in duplicated_data["tickets"] if t["id"] == tid), None)
        if not ticket:
            send_message(vk, user_id, f"❌ Тикет #{tid} не найден")
            return

        ticket["status"] = "declined"
        save_duplicated(duplicated_data)

        send_message(vk, ticket["user_id"], "❌ Ваше обращение отклонено.")
        send_message(vk, user_id, f"✅ Тикет #{tid} отклонён")
        return

    if text_lower.startswith("/бан"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Формат: /бан 1")
            return
        try:
            tid = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID — число")
            return

        ticket = next((t for t in duplicated_data["tickets"] if t["id"] == tid), None)
        if not ticket:
            send_message(vk, user_id, f"❌ Тикет #{tid} не найден")
            return

        ban_uid = ticket["user_id"]
        ticket["status"] = "banned"
        save_duplicated(duplicated_data)

        if ban_uid not in banned_data["users"]:
            banned_data["users"].append(ban_uid)
            save_banned(banned_data)

        try:
            vk.account.ban(owner_id=ban_uid)
        except Exception:
            pass

        send_message(vk, ban_uid, "⛔ Пользователь заблокировал вас.")
        send_message(vk, user_id,
                     f"⛔ {ticket['name']} заблокирован, тикет #{tid} закрыт")
        return

    if text_lower.startswith("/разбан"):
        parts = text.split()
        if len(parts) < 2:
            send_message(vk, user_id, "❌ Формат: /разбан 123456")
            return
        try:
            unban_id = int(parts[1])
        except ValueError:
            send_message(vk, user_id, "❌ ID — число")
            return

        if unban_id in banned_data["users"]:
            banned_data["users"].remove(unban_id)
            save_banned(banned_data)
        try:
            vk.account.unban(owner_id=unban_id)
        except Exception:
            pass

        name = get_user_name(vk, unban_id)
        send_message(vk, user_id, f"✅ {name} разблокирован")
        return

    if text_lower == "/баны":
        if not banned_data["users"]:
            send_message(vk, user_id, "📋 Банов нет.")
            return
        msg = "⛔ Забаненные:\n\n"
        for i, uid in enumerate(banned_data["users"], 1):
            name = get_user_name(vk, uid)
            msg += f"{i}. {name} (id{uid})\n"
        send_message(vk, user_id, msg)
        return

    if text_lower == "/очистить":
        duplicated_data["tickets"] = []
        duplicated_data["next_id"] = 1
        save_duplicated(duplicated_data)
        send_message(vk, user_id, "🗑 Все тикеты удалены.")
        return

    if text_lower.startswith("/рассылка"):
        broadcast_text = text[len("/рассылка"):].strip()
        if not broadcast_text:
            send_message(vk, user_id, "❌ Формат: /рассылка Привет!")
            return
        thread = threading.Thread(
            target=do_broadcast,
            args=(vk, broadcast_text, user_id),
            daemon=True
        )
        thread.start()
        return

    if text_lower == "/занят":
        settings["status"] = "busy"
        settings["custom_reply"] = ""
        save_settings(settings)
        send_message(vk, user_id, "🔴 Статус: занят")
        return

    if text_lower == "/свободен":
        settings["status"] = "default"
        settings["custom_reply"] = ""
        save_settings(settings)
        send_message(vk, user_id, "🟢 Статус: свободен")
        return

    if text_lower == "/стоп":
        settings["autoresponder_enabled"] = False
        save_settings(settings)
        send_message(vk, user_id, "⏸ Автоответчик ВЫКЛ")
        return

    if text_lower == "/старт":
        settings["autoresponder_enabled"] = True
        save_settings(settings)
        send_message(vk, user_id, "▶️ Автоответчик ВКЛ")
        return

    if text_lower.startswith("/автоответ"):
        custom = text[len("/автоответ"):].strip()
        if not custom:
            send_message(vk, user_id, "❌ Формат: /автоответ текст")
            return
        settings["custom_reply"] = custom
        save_settings(settings)
        send_message(vk, user_id, f"✅ Автоответ:\n\n{custom}")
        return

    if text_lower == "/сброс":
        settings["custom_reply"] = ""
        settings["status"] = "default"
        save_settings(settings)
        send_message(vk, user_id, "✅ Автоответ сброшен")
        return


def connect_vk():
    while True:
        try:
            print("[...] Подключаюсь...", flush=True)
            vk_session = vk_api.VkApi(token=TOKEN)
            vk = vk_session.get_api()
            info = vk.account.getProfileInfo()
            print(f"[OK] {info['first_name']} {info['last_name']}", flush=True)
            return vk_session, vk
        except Exception as e:
            print(f"[!] {e}", flush=True)
            time.sleep(10)


def main():
    print("=" * 50, flush=True)
    print("    VK Автоответчик v2.2", flush=True)
    print("=" * 50, flush=True)

    if not TOKEN or len(TOKEN) < 20:
        print("[!] Нет токена! Добавь VK_TOKEN", flush=True)
        return

    vk_session, vk = connect_vk()

    duplicated_data = load_duplicated()
    banned_data = load_banned()
    settings = load_settings()

    threading.Thread(
        target=auto_accept_friends,
        args=(vk,),
        daemon=True
    ).start()

    print(f"[i] Владелец: id{OWNER_ID}", flush=True)
    print("[>] Слушаю...", flush=True)
    print("-" * 50, flush=True)

    while True:
        try:
            longpoll = VkLongPoll(vk_session, mode=2)

            for event in longpoll.listen():
                if event.type != VkEventType.MESSAGE_NEW:
                    continue
                if event.from_me:
                    continue

                if event.from_chat:
                    try:
                        process_chat_message(vk, event)
                    except Exception as e:
                        print(f"[!] Чат: {e}", flush=True)
                    continue

                try:
                    process_message(vk, event,
                                    duplicated_data,
                                    banned_data,
                                    settings)
                except Exception as e:
                    print(f"[!] ЛС: {e}", flush=True)

        except KeyboardInterrupt:
            print("\n[X] Стоп", flush=True)
            return

        except Exception as e:
            print(f"[!] Обрыв: {e}", flush=True)
            time.sleep(10)
            try:
                vk_session, vk = connect_vk()
                threading.Thread(
                    target=auto_accept_friends,
                    args=(vk,),
                    daemon=True
                ).start()
            except Exception:
                pass


if __name__ == "__main__":
    main()
