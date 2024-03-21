import os
import sys
import time

import logging
import requests
from dotenv import load_dotenv
from telegram import Bot

from exceptions import (NoToketException,
                        GetApiAnswerException,
                        BadHomeworkStatusException)

load_dotenv()

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

RETRY_PERIOD = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/1"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}

# Вводим переменную с числом попыток обращения к API
attempt_number = 0

# Создаем логер
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens():
    """Проверяем доступность токенов."""
    if any(
        token is None for token in [
            PRACTICUM_TOKEN,
            TELEGRAM_TOKEN,
            TELEGRAM_CHAT_ID
        ]
    ):
        error_message = "Отсутствуют обязательные переменные окружения"
        logger.critical(error_message)
        raise NoToketException(error_message)


def send_message(bot, message):
    """Отправляем сообщение в телеграме."""
    chat_id = TELEGRAM_CHAT_ID
    try:
        bot.send_message(chat_id, message)
        logger.debug(f"Сообщение '{message}' в телеграме успешно отправлено")
    except Exception as error:
        logger.error(
            f"Ошибка отправки сообщения '{message}' в телеграме: {error}"
        )


def get_api_answer(timestamp):
    """Делаем запрос к API для получения информации о статусах проверки."""
    global attempt_number
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={"from_date": timestamp},
            timeout=RETRY_PERIOD,
        )
    except requests.RequestException as error:
        attempt_number += 1
        raise Exception(f"Ошибка запроса {error}")
    if response.status_code != 200:
        error_message = f"Ошибка запроса: код ответа {response.status_code}"
        logger.error(error_message)
        attempt_number += 1
        raise GetApiAnswerException(error_message)
    attempt_number = 0
    return response.json()


def check_response(response):
    """Проверяем ответ сервера на наличие ключей."""
    print(type(response))
    if not isinstance(response, dict):
        logger.error("Ответ пришел не в виде словаря")
        raise TypeError("Ответ пришел не в виде словаря")
    if response.get("homeworks") is None:
        logger.error("В ответе нет ключа homeworks")
        raise KeyError("В ответе нет ключа homeworks")
    if not isinstance(response["homeworks"], list):
        logger.error("Под ключом homeworks содержится не список")
        raise TypeError("Под ключом homeworks содержится не список")
    return True


def parse_status(homework):
    """Получаем информацию о конкретной домашней работе."""
    if homework.get("homework_name") is None:
        logger.error("В домашке нет ключа homework_name")
        raise KeyError("В домашке нет ключа homework_name")
    if (homework["status"] not in HOMEWORK_VERDICTS
            or homework["status"] is None):
        raise BadHomeworkStatusException("Неожиданный статус домашней работы")
    homework_name = homework["homework_name"]
    status = homework["status"]
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    # Проверяем доступны ли все необходимые токены
    # если нет, то прерываем выполнение программы
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    # timestamp = int(time.time())
    timestamp = 0

    while True:
        try:
            response = get_api_answer(timestamp)
            # Проверяем, что в ответе есть нужные ключи
            if check_response(response):
                for homework in response["homeworks"]:
                    message = parse_status(homework)
                    send_message(bot, message)
                # Присваиваем timestamp значение из текущего запроса
                timestamp = int(response["current_date"])
        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            # При ошибке запроса к API присылаем сообщение в ТГ
            # только 1 раз
            if attempt_number <= 1:
                send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
