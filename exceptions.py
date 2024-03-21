"""Кастомные ошибки."""


class NoToketException(Exception):
    """Отсутствуют обязательные переменные окружения."""


class GetApiAnswerException(Exception):
    """Ошибка запроса к API."""


class BadHomeworkStatusException(Exception):
    """Неожиданный статус домашней работы."""
