#!/usr/bin/env python
"""
Скрипт для проверки работы Celery.
Запускает тестовую задачу и проверяет подключение к Redis.
"""
import os
import sys
import time
import django
import redis
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Необходимо для импорта моделей Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'docs_metadata_enhancer.settings')
django.setup()

from docs_metadata_enhancer.celery import app as celery_app
from docs_metadata_enhancer.settings import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

def check_redis_connection():
    """Проверяет соединение с Redis."""
    logger.info("Проверка соединения с Redis...")
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=int(REDIS_PORT),
            password=REDIS_PASSWORD,
            socket_timeout=2
        )
        r.ping()
        logger.info(f"✅ Redis доступен по адресу {REDIS_HOST}:{REDIS_PORT}")
        return True
    except redis.exceptions.ConnectionError as e:
        logger.error(f"❌ Не удалось подключиться к Redis: {str(e)}")
        logger.error(f"Проверьте, что Redis запущен по адресу {REDIS_HOST}:{REDIS_PORT}")
        return False
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка при подключении к Redis: {str(e)}")
        return False

def check_task_execution():
    """Запускает тестовую задачу Celery и проверяет ее выполнение."""
    from docs_metadata_enhancer.celery import debug_task
    
    logger.info("Отправка тестовой задачи в Celery...")
    task = debug_task.delay()
    logger.info(f"Задача отправлена с ID: {task.id}")
    
    logger.info("Ожидание результата выполнения задачи...")
    max_wait = 10  # Максимальное время ожидания в секундах
    wait_interval = 0.5  # Интервал проверки статуса
    
    elapsed = 0
    while elapsed < max_wait:
        if task.ready():
            if task.successful():
                logger.info(f"✅ Задача выполнена успешно! Результат: {task.result}")
                return True
            else:
                logger.error(f"❌ Задача завершилась с ошибкой: {task.result}")
                return False
        
        time.sleep(wait_interval)
        elapsed += wait_interval
        sys.stdout.write(".")
        sys.stdout.flush()
    
    logger.error(f"❌ Превышено время ожидания {max_wait} сек. Задача не выполнена.")
    return False

def main():
    """Основная функция проверки Celery."""
    logger.info("=== Начало проверки Celery ===")
    
    # Проверка соединения с Redis
    if not check_redis_connection():
        logger.error("Проверка Redis не пройдена. Celery не сможет работать без Redis.")
        return False
    
    # Проверка выполнения задач
    if not check_task_execution():
        logger.error("Проверка выполнения задач не пройдена. Возможно, Celery worker не запущен.")
        logger.info("Попробуйте запустить Celery worker командой:")
        logger.info("celery -A docs_metadata_enhancer worker --loglevel=info --pool=solo")
        return False
    
    logger.info("=== Проверка Celery успешно завершена ===")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 