import logging
import os
import sys
import time
from contextlib import suppress
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

PRACTICUM_TOKEN = os.getenv("PRACTICUM_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Добавляем кортеж с перечислением обязательных токенов
required_tokens = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = "https://practicum.yandex.ru/api/user_api/homework_statuses/"
HEADERS = {"Authorization": f"OAuth {PRACTICUM_TOKEN}"}

HOMEWORK_VERDICTS = {
    "approved": "Работа проверена: ревьюеру всё понравилось. Ура!",
    "reviewing": "Работа взята на проверку ревьюером.",
    "rejected": "Работа проверена: у ревьюера есть замечания.",
}

# Создаем логер
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s - %(funcName)s - %(lineno)d'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens():
    """Проверяем доступность токенов."""
    missing_tokens = [
        token for token in required_tokens if not globals()[token]
    ]
    if missing_tokens:
        error_message = (
            "Отсутствуют переменные окружения: "
            f"{', '.join(missing_tokens)}"
        )
        logger.critical(error_message)
        raise ValueError(error_message)


def uniq_messages_only(func):
    """Декоратор контролирующий, чтобы не отправлялись одинаковые сообщения."""
    # Создаем переменную, в которую будем сохранять
    # последнее отправленное сообщение
    last_message = ''

    def wrapper(bot, message):
        """Обертка."""
        nonlocal last_message
        if message == last_message:
            logger.debug("Сообщение в телеграм не отправлено, "
                         "так как совпадает с предыдущим")
        else:
            last_message = message
            return func(bot, message)
    return wrapper


@uniq_messages_only
def send_message(bot, message):
    """Отправляем сообщение в телеграме."""
    logger.debug("Начало отправки сообщения в телеграм")
    bot.send_message(TELEGRAM_CHAT_ID, message)
    logger.debug(f"Сообщение '{message}' в телеграме успешно отправлено")


def get_api_answer(timestamp):
    """Делаем запрос к API для получения информации о статусах проверки."""
    logger.debug("Начало отправки запроса к API")
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={"from_date": timestamp},
            timeout=RETRY_PERIOD,
        )
    except requests.RequestException as error:
        raise ConnectionError("Ошибка запроса на эндпоинт "
                              f"{ENDPOINT}: {error}")
    if response.status_code != HTTPStatus.OK:
        error_message = (f"Ошибка запроса на эндпоинт {ENDPOINT}: "
                         f"код ответа {response.status_code}")
        raise ValueError(error_message)
    logger.debug("Успешное получение ответа API")
    return response.json()


def check_response(response):
    """Проверяем ответ сервера на наличие ключей."""
    logger.debug("Начало проверки запроса к API")
    if not isinstance(response, dict):
        raise TypeError("Ответ пришел не в виде словаря. "
                        f"Тип ответа: {type(response)}")
    if "homeworks" not in response:
        raise KeyError("В ответе нет ключа homeworks")
    if not isinstance(response["homeworks"], list):
        raise TypeError("Под ключом homeworks содержится не список "
                        f"Полученный тип: {type(response['homeworks'])}")


def parse_status(homework):
    """Получаем информацию о конкретной домашней работе."""
    logger.debug("Начало получения статуса")
    homework_status = homework.get("status")
    homework_name = homework.get("homework_name")
    if homework_name is None:
        raise KeyError("В домашке нет ключа homework_name")
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError("Неожиданный статус домашней работы. "
                         f"Полученный статус: {homework_status}")
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    # Проверяем доступны ли все необходимые токены
    # если нет, то прерываем выполнение программы
    check_tokens()
    bot = Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            # Проверяем, что в ответе есть нужные ключи
            check_response(response)
            # Проверяем, что получили не пустой список с домашками
            if response["homeworks"]:
                homework = response["homeworks"][0]
                message = parse_status(homework)
                send_message(bot, message)
            else:
                logger.debug("Получен пустой список домашек")

            # Если в ответе есть значение current_date, то присваиваем
            # timestamp значение из запроса
            timestamp = response.get("current_date", timestamp)
        except telegram.error.TelegramError as error:
            logger.error(
                f"Ошибка отправки сообщения '{message}' в телеграме: {error}"
            )
        except Exception as error:
            message = f"Сбой в работе программы: {error}"
            logger.error(message)
            with suppress(telegram.error.TelegramError):
                send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == "__main__":
    main()
