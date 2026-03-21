import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import time
import json
import os

# Токен берётся из переменных окружения Railway
TOKEN = os.getenv("VK_TOKEN", "vk1.a.mqK7Hhet4GaA6NxNlMbnc0YP2ZHC_18aTaVabwrFzfC6yBFQ4xwA3vdWqHtsMwCIg7Uk6CH934HgBKxtpHF1qjn8Zpk1vNdsWKSlPSCQPvp1vz-lELEAcm85wBEtr9iOmF-zUKRPK_0Epw_Pg0a6eCgOCaYwp_Wp3Vd0VbgaxRNxRg8oV90PQgY-C6vYdJTELxIL2P0fy17-KoMWadkCfQ")

DUPLICATED_FILE = "duplicated_chats.json"
greeted_users = set()


def load_duplicated():
    if os.path.exists(DUPLICATED_FILE):
        try:
            with open(DUPLICATED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "users" not in data:
                    data["users"] = []
                if "details" not in data:
                    data["details"] = {}
                return data
        except Exception:
            pass
    return {"users": [], "details": {}}


def save_duplicated(data):
    with open(DUPLICATED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_name(vk, user_id):
    try:
        user_info = vk.users.get(user_ids=user_id)
        if user_info:
            return f"{user_info[0]['first_name']} {user_info[0]['last_name']}"
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
            print(f"[OK] Отправлено -> {user_id}", flush=True)
            return True
        except vk_api.exceptions.ApiError as e:
            print(f"[ОШИБКА API] {e}", flush=True)
            return False
        except Exception as e:
            print(f"[СЕТЬ] Попытка {attempt + 1}/3: {e}", flush=True)
            time.sleep(3)
    return False


def process_message(vk, event, duplicated_data):
    user_id = event.user_id
    text = event.text.strip().lower() if event.text else ""
    user_name = get_user_name(vk, user_id)

    print(f"[<] {user_name} ({user_id}): {event.text}", flush=True)

    AUTO_REPLY = (
        "Привет! Спасибо за обращение, ожидай ответа!\n\n"
        "🕐 Появляюсь в сети несколько раз в час! Жди, "
        "но ты можешь затеряться среди других чатов.\n\n"
        "📌 Спустя пару часов пиши: /продублировать — и ожидай ответа!"
    )

    DUPLICATE_OK = (
        "✅ Твоё обращение продублировано!\n"
        "Я обязательно отвечу, как только появлюсь в сети."
    )

    DUPLICATE_ALREADY = (
        "ℹ️ Твоё обращение уже было продублировано ранее.\n"
        "Ожидай ответа, я скоро появлюсь!"
    )

    if text in ["/продублировать", "/дублировать"]:
        if user_id not in duplicated_data["users"]:
            duplicated_data["users"].append(user_id)
            duplicated_data["details"][str(user_id)] = {
                "name": user_name,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            save_duplicated(duplicated_data)
            send_message(vk, user_id, DUPLICATE_OK)
            print(f"[+] {user_name} добавлен в дублированные", flush=True)
        else:
            send_message(vk, user_id, DUPLICATE_ALREADY)
        return

    if text == "/статус":
        if duplicated_data["users"]:
            msg = "📋 Дублированные обращения:\n\n"
            for i, uid in enumerate(duplicated_data["users"], 1):
                detail = duplicated_data["details"].get(str(uid), {})
                name = detail.get("name", f"ID {uid}")
                dt = detail.get("time", "?")
                msg += f"{i}. {name} (vk.com/id{uid}) — {dt}\n"
            send_message(vk, user_id, msg)
        else:
            send_message(vk, user_id, "📋 Список дублированных пуст.")
        return

    if text == "/очистить":
        duplicated_data["users"] = []
        duplicated_data["details"] = {}
        save_duplicated(duplicated_data)
        send_message(vk, user_id, "🗑 Список дублированных очищен.")
        return

    if user_id not in greeted_users:
        greeted_users.add(user_id)
        send_message(vk, user_id, AUTO_REPLY)


def connect_vk():
    while True:
        try:
            print("[...] Подключаюсь к ВК...", flush=True)
            vk_session = vk_api.VkApi(token=TOKEN)
            vk = vk_session.get_api()
            info = vk.account.getProfileInfo()
            print(f"[OK] Вошли как: {info['first_name']} {info['last_name']}", flush=True)
            return vk_session, vk
        except Exception as e:
            print(f"[ОШИБКА] {e}", flush=True)
            print("[i] Повтор через 10 сек...", flush=True)
            time.sleep(10)


def main():
    print("=" * 50, flush=True)
    print("       VK Автоответчик (Railway)", flush=True)
    print("=" * 50, flush=True)

    if not TOKEN or len(TOKEN) < 20:
        print("", flush=True)
        print("[!] ТОКЕН НЕ НАЙДЕН!", flush=True)
        print("", flush=True)
        print("Добавь переменную VK_TOKEN в Railway:", flush=True)
        print("Railway -> Variables -> VK_TOKEN = твой_токен", flush=True)
        return

    vk_session, vk = connect_vk()
    duplicated_data = load_duplicated()

    print("", flush=True)
    print("[>] Бот запущен и слушает сообщения...", flush=True)
    print("-" * 50, flush=True)

    while True:
        try:
            longpoll = VkLongPoll(vk_session)

            for event in longpoll.listen():
                if event.type != VkEventType.MESSAGE_NEW:
                    continue
                if event.from_me:
                    continue
                if event.from_chat:
                    continue

                try:
                    process_message(vk, event, duplicated_data)
                except Exception as e:
                    print(f"[ОШИБКА] Обработка: {e}", flush=True)

        except KeyboardInterrupt:
            print("\n[X] Бот остановлен", flush=True)
            return

        except Exception as e:
            print(f"\n[!] Потеря соединения: {e}", flush=True)
            print("[i] Переподключение через 5 сек...", flush=True)
            time.sleep(5)

            try:
                vk_session, vk = connect_vk()
                print("[OK] Переподключился!", flush=True)
            except Exception:
                pass


if __name__ == "__main__":
    main()
