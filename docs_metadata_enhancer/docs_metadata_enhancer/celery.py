import os
import time
import socket
import platform
from celery import Celery
from celery.signals import worker_ready, worker_shutdown, setup_logging
from kombu import Connection
import logging
from kombu.exceptions import OperationalError

# Настройка логирования для Celery
logger = logging.getLogger('celery')

# Устанавливаем переменную окружения для настроек Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'docs_metadata_enhancer.settings')

# Создаем экземпляр Celery
app = Celery('docs_metadata_enhancer')

# Загружаем настройки из файла settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')

# Проверяем, работает ли Redis
def check_redis_connection():
    try:
        from django.conf import settings
        # Получаем URL брокера из настроек
        broker_url = settings.CELERY_BROKER_URL
        with Connection(broker_url) as conn:
            conn.connect()
            return True
    except OperationalError as e:
        logger.error(f"Ошибка подключения к Redis: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при проверке Redis: {str(e)}")
        return False

# Автоматически находим и регистрируем задачи в приложениях Django
app.autodiscover_tasks()

# Настройки для платформы Windows
if platform.system() == 'Windows':
    app.conf.task_always_eager = not check_redis_connection()
    app.conf.broker_connection_retry = False  # Отключаем повторные попытки для более быстрого выявления проблем
    app.conf.broker_connection_max_retries = 1  # Максимум 1 повторная попытка
    app.conf.worker_concurrency = 1
    app.conf.worker_prefetch_multiplier = 1
    app.conf.task_send_sent_event = True  # Для лучшего отслеживания задач

# Настройка повторных попыток для задач
app.conf.task_acks_late = True  # Подтверждение задач только после успешного выполнения
app.conf.task_reject_on_worker_lost = True  # Повторный запуск задач при потере воркера
app.conf.task_default_retry_delay = 30  # Задержка перед повторной попыткой (секунды)
app.conf.task_max_retries = 3  # Максимальное количество повторных попыток

# Обработчик логирования
@setup_logging.connect
def setup_logging_handler(**kwargs):
    logger.info(f"Настройка логирования Celery на {platform.system()}")

# Обработчики сигналов для логирования
@worker_ready.connect
def worker_ready_handler(**kwargs):
    logger.info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Celery worker готов к обработке задач")
    
    # Проверяем, включен ли режим eager_execution
    if app.conf.task_always_eager:
        logger.warning("ВНИМАНИЕ: Celery работает в режиме EAGER (синхронное выполнение задач)!")
        logger.warning("Это означает, что Redis недоступен, и задачи будут выполняться синхронно.")

@worker_shutdown.connect
def worker_shutdown_handler(**kwargs):
    logger.info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Celery worker завершает работу")

@app.task(bind=True)
def debug_task(self):
    """Тестовая задача для проверки работы Celery."""
    hostname = socket.gethostname()
    return f"Тестовая задача выполнена на {hostname} в {time.strftime('%Y-%m-%d %H:%M:%S')}"
