import os
import logging
import sys
import time
from http import HTTPStatus

from dotenv import load_dotenv
import telegram
import requests


class ApiError(Exception):
    ...


class ApiCodeError(Exception):
    ...


class ConvertError(Exception):
    def __init__(self, text):
        self.txt = f'Ответ API не конвертируется в json. {text}'
    ...


class MsgNotSendError(Exception):
    def __init__(self, text):
        self.txt = f'Сообщение не отправлено. {text}'
    ...


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }
    for token_key, token_value in tokens.items():
        if not token_value:
            err = f'Отсутствует обязательная переменная окружения {token_key}'
            logging.critical(err)
            sys.exit(err)


def send_message(bot, message):
    """Отправка сообщения о статусе ботом."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.error.TelegramError:
        logging.error('Сообщение не отправлено')
        raise MsgNotSendError()
    else:
        logging.debug('Сообщение отправлено')


def get_api_answer(timestamp):
    """Возврат ответа от API."""
    try:
        api_answer = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        api_answer_status_code = api_answer.status_code
        if api_answer_status_code != HTTPStatus.OK:
            logging.error(
                f'API домашки возвращает код {api_answer_status_code}'
            )
            raise ApiCodeError(
                f'API домашки возвращает код {api_answer_status_code}'
            )
    except requests.RequestException:
        logging.error(f'Не удалось получить ответ'
                      f'endpoint={ENDPOINT}'
                      f'headers={HEADERS}'
                      f'params from_date={timestamp}'
                      )
        raise ApiError('Не удалось получить ответ')
    else:
        try:
            return api_answer.json()
        except TypeError():
            logging.error('Ответ API не конвертируется в json')
            raise ConvertError()


def check_response(response):
    """Проверка response."""
    if not isinstance(response, dict):
        logging.error('В респонсе получен не словарь')
        raise TypeError('В респонсе получен не словарь')
    if 'current_date'not in response.keys():
        logging.error('В респонсе нет нужного ключа - current_date')
        raise KeyError('В респонсе нет нужного ключа - current_date')
    if 'homeworks'not in response.keys():
        logging.error('В респонсе нет нужного ключа - homeworks')
        raise KeyError('В респонсе нет нужного ключа - homeworks')
    if not isinstance(response['homeworks'], list):
        logging.error('В response[homeworks] получен не список')
        raise TypeError('В response[homeworks] получен не список')
    if response['homeworks']:
        logging.debug('Обновлений нет')
    return response.get('homeworks')


def parse_status(homework):
    """Расшифровка статуса проверки работы."""
    homework_keys = [
        'homework_name',
        'status'
    ]
    for homework_key in homework_keys:
        if homework_key not in homework.keys():
            logging.error(
                f'В homework нет ключа {homework_key}')
            raise KeyError(
                f'В homework нет ключа {homework_key}'
            )
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS.keys():
        logging.error(
            'API домашки вернул недокументированный статус/без статуса'
        )
        raise KeyError(
            'API домашки вернул недокументированный статус/без статуса'
        )
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    send_message(bot, 'Бот включен')
    timestamp = int(time.time()) - RETRY_PERIOD
    status_old = ''

    while True:
        try:
            timestamp_now = int(time.time())
            response_now = check_response(get_api_answer(timestamp))
            if response_now:
                status_now = parse_status(response_now[0])
                if status_now != status_old:
                    send_message(bot, status_now)
                    status_old = status_now
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            logging.error(message)
        finally:
            timestamp = timestamp_now
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.FileHandler(filename='logs.log', mode='w'),
            logging.StreamHandler(stream=sys.stdout)
        ]
    )
    main()
