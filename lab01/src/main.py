import os
import csv
import json
import time
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# НАСТРОЙКИ
# ============================================================

load_dotenv()

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
MODEL_NAME = os.getenv("LLM_MODEL")

if not API_KEY:
    raise ValueError("Не указан LLM_API_KEY в .env")

if not BASE_URL:
    raise ValueError("Не указан LLM_BASE_URL в .env")

if not MODEL_NAME:
    raise ValueError("Не указан LLM_MODEL в .env")


# ============================================================
# API-КЛИЕНТ
# ============================================================

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=600.0
)


# ============================================================
# 10 ТЕСТОВЫХ ЗАПРОСОВ
# ============================================================

prompts = [

    """
Объясни студенту 4 курса разницу между хешированием
и симметричным шифрованием.
Ответ должен содержать не более 120 слов.
""",

    """
Определи тип события:

После 15 неудачных попыток входа с одного IP-адреса
был выполнен успешный вход администратора.

Выбери один вариант:
норма / подозрительно / критично

Кратко объясни свой выбор.
""",

    """
Сожми следующий текст до 5 тезисов:

Информационная безопасность включает комплекс технических,
организационных и правовых мер, направленных на защиту информации.
Основными свойствами защищаемой информации являются
конфиденциальность, целостность и доступность.
Для защиты информационных систем применяются разграничение доступа,
антивирусные средства, межсетевые экраны, резервное копирование,
мониторинг событий и обучение сотрудников.
Особое внимание необходимо уделять человеческому фактору,
поскольку фишинг и социальная инженерия остаются распространёнными
способами атак.
""",

    """
Извлеки данные из события:

2026-09-16 10:25:31 пользователь admin
успешно вошёл в систему с IP-адреса 192.168.1.55.

Верни только JSON следующего вида:

{
    "ip": "",
    "user": "",
    "timestamp": "",
    "event_type": ""
}
""",

    """
Напиши Python-функцию, которая получает строку
и возвращает её SHA-256 хеш в шестнадцатеричном формате.

Используй стандартную библиотеку Python.
""",

    """
Найди ошибку в следующем Python-коде и исправь её:

def divide(a, b):
    return a / b

print(divide(10, 0))

Объясни причину ошибки и покажи исправленный вариант.
""",

    """
Предложи краткий план первичного анализа подозрительного
входа в корпоративную информационную систему.

Укажи действия специалиста по информационной безопасности
в правильной последовательности.
""",

    """
Назови 5 основных рисков использования внешней LLM
для анализа внутренних документов организации.

Для каждого риска дай краткое пояснение.
""",

    """
Сформулируй краткое уведомление сотрудникам организации
о запрете передачи паролей, API-ключей и других секретных
данных в публичные AI-сервисы.

Стиль должен быть официально-деловым.
""",

    """
Оцени 4 риска AI-агента, имеющего доступ
к корпоративной электронной почте.

Ответь ТОЛЬКО таблицей Markdown со столбцами:

| риск | вероятность | ущерб | мера защиты |

Никакого текста до или после таблицы.
"""
]


# ============================================================
# ФУНКЦИЯ ЗАПРОСА К МОДЕЛИ
# ============================================================

def ask_model(prompt):

    started = time.perf_counter()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": (
                    "Отвечай точно и по существу. "
                    "Не выполняй длинные внутренние рассуждения. "
                    "Сразу дай итоговый ответ."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
        max_tokens=2000
    )

    elapsed = time.perf_counter() - started

    message = response.choices[0].message

    answer = message.content or ""

    if not answer.strip():
        raise ValueError(
            "Модель завершила генерацию, "
            "но не вернула финальный текст ответа."
        )

    return answer, elapsed


# ============================================================
# ЗАПУСК ЭКСПЕРИМЕНТА
# ============================================================

results = []

print("=" * 60)
print("ТЕСТИРОВАНИЕ LLM ЧЕРЕЗ API")
print("=" * 60)

print(f"\nМодель: {MODEL_NAME}")
print(f"Количество запросов: {len(prompts)}")


for prompt_id, prompt in enumerate(prompts, start=1):

    print("\n" + "-" * 60)
    print(f"Запрос {prompt_id}/{len(prompts)}")

    try:

        answer, latency = ask_model(
            prompt.strip()
        )

        print(f"Время ответа: {latency:.3f} сек.")
        print("Статус: успешно")

        print("\nОтвет модели:")
        print(answer)

        results.append({
            "model": MODEL_NAME,
            "prompt_id": prompt_id,
            "prompt": prompt.strip(),
            "latency": round(latency, 3),
            "answer": answer,
            "error": "",
            "correctness": "",
            "completeness": "",
            "instruction_following": "",
            "usefulness": "",
            "total_score": ""
        })

    except Exception as exc:

        error_text = str(exc)

        print("Статус: ошибка")
        print(f"Ошибка: {error_text}")

        results.append({
            "model": MODEL_NAME,
            "prompt_id": prompt_id,
            "prompt": prompt.strip(),
            "latency": "",
            "answer": "",
            "error": error_text,
            "correctness": "",
            "completeness": "",
            "instruction_following": "",
            "usefulness": "",
            "total_score": ""
        })


# ============================================================
# СОЗДАНИЕ ПАПКИ RESULTS
# ============================================================

os.makedirs(
    "results",
    exist_ok=True
)


# ============================================================
# ИМЕНА ФАЙЛОВ
# ============================================================

timestamp = datetime.now().strftime(
    "%Y-%m-%d_%H-%M-%S"
)

safe_model_name = (
    MODEL_NAME
    .replace("/", "_")
    .replace("\\", "_")
    .replace(":", "_")
)

csv_filename = (
    f"results/"
    f"{safe_model_name}_{timestamp}.csv"
)

json_filename = (
    f"results/"
    f"{safe_model_name}_{timestamp}.json"
)


# ============================================================
# ЭКСПОРТ В CSV
# ============================================================

fieldnames = [
    "model",
    "prompt_id",
    "prompt",
    "latency",
    "answer",
    "error",
    "correctness",
    "completeness",
    "instruction_following",
    "usefulness",
    "total_score"
]


with open(
    csv_filename,
    "w",
    newline="",
    encoding="utf-8-sig"
) as csv_file:

    writer = csv.DictWriter(
        csv_file,
        fieldnames=fieldnames
    )

    writer.writeheader()

    writer.writerows(
        results
    )


# ============================================================
# ЭКСПОРТ В JSON
# ============================================================

with open(
    json_filename,
    "w",
    encoding="utf-8"
) as json_file:

    json.dump(
        results,
        json_file,
        ensure_ascii=False,
        indent=4
    )


# ============================================================
# СТАТИСТИКА
# ============================================================

successful = [
    result
    for result in results
    if result["answer"] != ""
    and result["error"] == ""
]

errors = [
    result
    for result in results
    if result["error"] != ""
]


print("\n" + "=" * 60)
print("ЭКСПЕРИМЕНТ ЗАВЕРШЁН")
print("=" * 60)

print(f"\nМодель: {MODEL_NAME}")

print(
    f"Успешных запросов: "
    f"{len(successful)}/{len(prompts)}"
)

print(
    f"Ошибок: "
    f"{len(errors)}"
)


# ============================================================
# СРЕДНЕЕ ВРЕМЯ ОТВЕТА
# ============================================================

if successful:

    average_latency = sum(
        result["latency"]
        for result in successful
    ) / len(successful)

    fastest = min(
        result["latency"]
        for result in successful
    )

    slowest = max(
        result["latency"]
        for result in successful
    )

    print(
        f"Среднее время ответа: "
        f"{average_latency:.3f} сек."
    )

    print(
        f"Самый быстрый ответ: "
        f"{fastest:.3f} сек."
    )

    print(
        f"Самый медленный ответ: "
        f"{slowest:.3f} сек."
    )


# ============================================================
# ВЫВОД ОШИБОК
# ============================================================

if errors:

    print("\nЗапросы с ошибками:")

    for result in errors:

        print(
            f"Запрос {result['prompt_id']}: "
            f"{result['error']}"
        )


# ============================================================
# ПУТИ К РЕЗУЛЬТАТАМ
# ============================================================

print("\nРезультаты сохранены:")

print(
    f"CSV:  {csv_filename}"
)

print(
    f"JSON: {json_filename}"
)

print("\nГотово.")