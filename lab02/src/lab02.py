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


client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=600.0
)


# ============================================================
# ОБЩИЙ СПИСОК РЕЗУЛЬТАТОВ
# ============================================================

results = []


# ============================================================
# ФУНКЦИЯ ЗАПРОСА К МОДЕЛИ
# ============================================================

def ask_model(
        prompt,
        system="Отвечай точно и по существу.",
        temperature=None,
        max_tokens=None
):
    kwargs = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": system
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    # Добавляем параметры только при необходимости
    if temperature is not None:
        kwargs["temperature"] = temperature

    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    started = time.perf_counter()

    response = client.chat.completions.create(
        **kwargs
    )

    elapsed = time.perf_counter() - started

    message = response.choices[0].message

    answer = message.content or ""

    finish_reason = response.choices[0].finish_reason

    # Информация о токенах, если LM Studio её возвращает
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None

    if response.usage:
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        total_tokens = response.usage.total_tokens

    return {
        "answer": answer,
        "latency": round(elapsed, 3),
        "finish_reason": finish_reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens
    }


# ============================================================
# ФУНКЦИЯ СОХРАНЕНИЯ РЕЗУЛЬТАТА
# ============================================================

def save_result(
        experiment,
        prompt,
        system_id="",
        system_prompt="",
        temperature=None,
        max_tokens=None,
        repeat=1,
        response_data=None,
        error=""
):
    if response_data is None:
        response_data = {}

    results.append({
        "model": MODEL_NAME,
        "experiment": experiment,
        "system_id": system_id,
        "system_prompt": system_prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "repeat": repeat,
        "prompt": prompt,
        "latency_s": response_data.get("latency", ""),
        "finish_reason": response_data.get("finish_reason", ""),
        "prompt_tokens": response_data.get("prompt_tokens", ""),
        "completion_tokens": response_data.get("completion_tokens", ""),
        "total_tokens": response_data.get("total_tokens", ""),
        "answer": response_data.get("answer", ""),
        "error": error
    })


# ============================================================
# ВЫВОД ЗАГОЛОВКА
# ============================================================

print("=" * 70)
print("ЛАБОРАТОРНАЯ РАБОТА № 2")
print("ПАРАМЕТРЫ ГЕНЕРАЦИИ И КОНФИГУРАЦИЯ LLM")
print("=" * 70)

print(f"\nМодель: {MODEL_NAME}")


# ============================================================
# ЭТАП 1
# БАЗОВАЯ КОНФИГУРАЦИЯ
# ============================================================

print("\n" + "=" * 70)
print("ЭТАП 1. БАЗОВАЯ КОНФИГУРАЦИЯ")
print("=" * 70)


base_prompts = [

    """
Объясни разницу между хешированием и симметричным шифрованием.
Ответ дай кратко.
""",

    """
Оцени событие информационной безопасности:
после 15 неудачных попыток входа был выполнен
успешный вход администратора.
""",

    """
Назови основные риски использования внешней LLM
для обработки внутренних документов организации.
"""
]


for i, prompt in enumerate(base_prompts, start=1):

    print(f"\nБазовый запрос {i}/3")

    try:

        response_data = ask_model(
            prompt=prompt.strip()
        )

        print(
            f"Время: "
            f"{response_data['latency']} сек."
        )

        print("Ответ:")
        print(response_data["answer"])

        save_result(
            experiment="baseline",
            prompt=prompt.strip(),
            repeat=i,
            response_data=response_data
        )

    except Exception as exc:

        print(f"Ошибка: {exc}")

        save_result(
            experiment="baseline",
            prompt=prompt.strip(),
            repeat=i,
            error=str(exc)
        )


# ============================================================
# ЭТАП 2
# ВЛИЯНИЕ SYSTEM PROMPT
# ============================================================

print("\n" + "=" * 70)
print("ЭТАП 2. SYSTEM PROMPT")
print("=" * 70)


system_user_prompt = """
Событие: в 03:17 зафиксировано 25 неудачных попыток
входа в учётную запись admin с одного IP,
после чего произошёл успешный вход.

Проанализируй ситуацию.
""".strip()


systems = [

    (
        "sys_01",
        """
Отвечай на запрос пользователя.
""".strip()
    ),

    (
        "sys_02",
        """
Ты ассистент аналитика информационной безопасности.
Отвечай не более чем в 5 пунктах.
Для каждого пункта укажи риск и рекомендуемое действие.
""".strip()
    ),

    (
        "sys_03",
        """
Ты ассистент аналитика информационной безопасности.
Не выдумывай недостающие данные.
Явно отделяй факты от предположений.

Ответ верни строго в формате:

Факты:
Гипотезы:
Действия:
""".strip()
    )
]


for system_id, system_prompt in systems:

    print(f"\nSystem prompt: {system_id}")

    try:

        response_data = ask_model(
            prompt=system_user_prompt,
            system=system_prompt
        )

        print(
            f"Время: "
            f"{response_data['latency']} сек."
        )

        print("Ответ:")
        print(response_data["answer"])

        save_result(
            experiment="system_prompt",
            prompt=system_user_prompt,
            system_id=system_id,
            system_prompt=system_prompt,
            repeat=1,
            response_data=response_data
        )

    except Exception as exc:

        print(f"Ошибка: {exc}")

        save_result(
            experiment="system_prompt",
            prompt=system_user_prompt,
            system_id=system_id,
            system_prompt=system_prompt,
            repeat=1,
            error=str(exc)
        )


# ============================================================
# ЭТАП 3
# TEMPERATURE
# ============================================================

print("\n" + "=" * 70)
print("ЭТАП 3. TEMPERATURE")
print("=" * 70)


temperature_prompt = """
Предложи пять названий сервиса для автоматического анализа
журналов событий информационной безопасности.

Для каждого названия дай пояснение в одном предложении.
""".strip()


temperature_values = [
    0.0,
    0.3,
    0.7,
    1.0
]


for temperature in temperature_values:

    print("\n" + "-" * 70)
    print(f"TEMPERATURE = {temperature}")
    print("-" * 70)

    for repeat in range(1, 6):

        print(
            f"\nПовтор {repeat}/5 "
            f"при temperature={temperature}"
        )

        try:

            response_data = ask_model(
                prompt=temperature_prompt,
                system=(
                    "Предлагай осмысленные варианты. "
                    "Соблюдай формат пользовательского задания."
                ),
                temperature=temperature,
                max_tokens=600
            )

            print(
                f"Время: "
                f"{response_data['latency']} сек."
            )

            print("Ответ:")
            print(response_data["answer"])

            save_result(
                experiment="temperature",
                prompt=temperature_prompt,
                system_id="temp_system",
                system_prompt=(
                    "Предлагай осмысленные варианты. "
                    "Соблюдай формат пользовательского задания."
                ),
                temperature=temperature,
                max_tokens=600,
                repeat=repeat,
                response_data=response_data
            )

        except Exception as exc:

            print(f"Ошибка: {exc}")

            save_result(
                experiment="temperature",
                prompt=temperature_prompt,
                system_id="temp_system",
                system_prompt=(
                    "Предлагай осмысленные варианты. "
                    "Соблюдай формат пользовательского задания."
                ),
                temperature=temperature,
                max_tokens=600,
                repeat=repeat,
                error=str(exc)
            )


# ============================================================
# ЭТАП 4
# ОГРАНИЧЕНИЕ ДЛИНЫ ОТВЕТА
# ============================================================

print("\n" + "=" * 70)
print("ЭТАП 4. ОГРАНИЧЕНИЕ ДЛИНЫ")
print("=" * 70)


length_prompt = """
Объясни студенту 4 курса архитектуру RAG-системы:

1. ingestion
2. chunking
3. embeddings
4. vector database
5. retrieval
6. prompt construction
7. generation

Для каждого этапа укажи:
- назначение;
- одну типичную ошибку.
""".strip()


token_limits = [
    100,
    300,
    800
]


for max_tokens in token_limits:

    print("\n" + "-" * 70)
    print(f"MAX_TOKENS = {max_tokens}")
    print("-" * 70)

    try:

        response_data = ask_model(
            prompt=length_prompt,
            system=(
                "Объясняй технически корректно, "
                "структурированно и понятно студенту."
            ),
            temperature=0.2,
            max_tokens=max_tokens
        )

        print(
            f"Время: "
            f"{response_data['latency']} сек."
        )

        print(
            f"Причина завершения: "
            f"{response_data['finish_reason']}"
        )

        print("Ответ:")
        print(response_data["answer"])

        save_result(
            experiment="max_tokens",
            prompt=length_prompt,
            system_id="length_system",
            system_prompt=(
                "Объясняй технически корректно, "
                "структурированно и понятно студенту."
            ),
            temperature=0.2,
            max_tokens=max_tokens,
            repeat=1,
            response_data=response_data
        )

    except Exception as exc:

        print(f"Ошибка: {exc}")

        save_result(
            experiment="max_tokens",
            prompt=length_prompt,
            system_id="length_system",
            system_prompt=(
                "Объясняй технически корректно, "
                "структурированно и понятно студенту."
            ),
            temperature=0.2,
            max_tokens=max_tokens,
            repeat=1,
            error=str(exc)
        )


# ============================================================
# ЭТАП 5
# ПРАКТИЧЕСКАЯ КОНФИГУРАЦИЯ
# ============================================================

print("\n" + "=" * 70)
print("ЭТАП 5. ПРАКТИЧЕСКАЯ КОНФИГУРАЦИЯ")
print("=" * 70)


practical_system = """
Ты ассистент аналитика информационной безопасности.

Не выдумывай недостающие данные.
Отделяй факты от предположений.
Отвечай кратко и структурированно.

Формат ответа:

Факты:
- ...

Гипотезы:
- ...

Рекомендуемые действия:
- ...
""".strip()


practical_prompt = """
Событие:
в 03:17 зафиксировано 25 неудачных попыток входа
в учётную запись admin с одного IP-адреса,
после чего произошёл успешный вход.

Проведи первичный анализ события.
""".strip()


try:

    response_data = ask_model(
        prompt=practical_prompt,
        system=practical_system,
        temperature=0.2,
        max_tokens=400
    )

    print(
        f"Время: "
        f"{response_data['latency']} сек."
    )

    print("Ответ:")
    print(response_data["answer"])

    save_result(
        experiment="practical_configuration",
        prompt=practical_prompt,
        system_id="practical_01",
        system_prompt=practical_system,
        temperature=0.2,
        max_tokens=400,
        repeat=1,
        response_data=response_data
    )

except Exception as exc:

    print(f"Ошибка: {exc}")

    save_result(
        experiment="practical_configuration",
        prompt=practical_prompt,
        system_id="practical_01",
        system_prompt=practical_system,
        temperature=0.2,
        max_tokens=400,
        repeat=1,
        error=str(exc)
    )


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
    f"lab02_{safe_model_name}_{timestamp}.csv"
)


json_filename = (
    f"results/"
    f"lab02_{safe_model_name}_{timestamp}.json"
)


# ============================================================
# CSV
# ============================================================

fieldnames = [
    "model",
    "experiment",
    "system_id",
    "system_prompt",
    "temperature",
    "max_tokens",
    "repeat",
    "prompt",
    "latency_s",
    "finish_reason",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "answer",
    "error"
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
# JSON
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
# КРАТКАЯ СТАТИСТИКА
# ============================================================

successful = [
    item
    for item in results
    if item["error"] == ""
]

errors = [
    item
    for item in results
    if item["error"] != ""
]


print("\n" + "=" * 70)
print("ЛАБОРАТОРНАЯ РАБОТА ЗАВЕРШЕНА")
print("=" * 70)

print(
    f"\nВсего экспериментов: "
    f"{len(results)}"
)

print(
    f"Успешно: "
    f"{len(successful)}"
)

print(
    f"Ошибок: "
    f"{len(errors)}"
)


if successful:

    average_latency = sum(
        float(item["latency_s"])
        for item in successful
        if item["latency_s"] != ""
    ) / len(successful)

    print(
        f"Средняя задержка: "
        f"{average_latency:.3f} сек."
    )


# ============================================================
# СТАТИСТИКА TEMPERATURE
# ============================================================

print("\n" + "=" * 70)
print("КРАТКАЯ СТАТИСТИКА TEMPERATURE")
print("=" * 70)


for temperature in temperature_values:

    temp_results = [
        item
        for item in results
        if item["experiment"] == "temperature"
        and item["temperature"] == temperature
        and item["error"] == ""
    ]

    if not temp_results:
        continue

    average_temp_latency = sum(
        item["latency_s"]
        for item in temp_results
    ) / len(temp_results)

    # Уникальность считаем по полному тексту ответа
    unique_answers = len(
        set(
            item["answer"].strip()
            for item in temp_results
        )
    )

    print(
        f"\nTemperature: {temperature}"
    )

    print(
        f"Успешных повторов: "
        f"{len(temp_results)}/5"
    )

    print(
        f"Уникальных ответов: "
        f"{unique_answers}"
    )

    print(
        f"Средняя задержка: "
        f"{average_temp_latency:.3f} сек."
    )


# ============================================================
# ОШИБКИ
# ============================================================

if errors:

    print("\n" + "=" * 70)
    print("ОШИБКИ")
    print("=" * 70)

    for item in errors:

        print(
            f"\nЭксперимент: "
            f"{item['experiment']}"
        )

        print(
            f"Temperature: "
            f"{item['temperature']}"
        )

        print(
            f"Max tokens: "
            f"{item['max_tokens']}"
        )

        print(
            f"Ошибка: "
            f"{item['error']}"
        )


# ============================================================
# ФАЙЛЫ
# ============================================================

print("\n" + "=" * 70)
print("РЕЗУЛЬТАТЫ СОХРАНЕНЫ")
print("=" * 70)

print(
    f"\nCSV:  {csv_filename}"
)

print(
    f"JSON: {json_filename}"
)

print("\nГотово.")