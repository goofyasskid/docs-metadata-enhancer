#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import subprocess
import threading
import time
import signal
import socket
from django.core.management import execute_from_command_line

# Флаг для предотвращения повторного запуска Celery
CELERY_STARTED = False
CELERY_PROCESS = None

def is_redis_running():
    """Проверяет, запущен ли Redis сервер."""
    try:
        # Получаем настройки Redis из settings
        from docs_metadata_enhancer.settings import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
        
        # Создаем соединение с Redis для проверки доступности
        import redis
        r = redis.Redis(
            host=REDIS_HOST,
            port=int(REDIS_PORT),
            password=REDIS_PASSWORD,
            socket_timeout=2
        )
        r.ping()
        return True
    except (ImportError, redis.exceptions.ConnectionError, socket.error) as e:
        print(f"Ошибка подключения к Redis: {str(e)}")
        return False
    except Exception as e:
        print(f"Неизвестная ошибка при проверке Redis: {str(e)}")
        return False

def start_celery():
    """Запускает Celery worker с пулом solo, возвращает процесс."""
    global CELERY_STARTED, CELERY_PROCESS
    if CELERY_STARTED:
        print("Celery worker уже запущен, пропускаем повторный запуск.")
        return CELERY_PROCESS

    # Проверяем работоспособность Redis перед запуском Celery
    if not is_redis_running():
        print("ВНИМАНИЕ: Redis недоступен! Celery не будет запущен.")
        print("Django будет работать без возможности фоновой обработки задач.")
        print("Для запуска Redis, установите и настройте сервер Redis, либо запустите docker-контейнер с Redis.")
        # Не запускаем Celery, но позволяем серверу запуститься
        return None

    print("Запуск Celery worker...")
    CELERY_STARTED = True

    # Запускаем Celery worker с --pool=solo для Windows
    celery_command = [
        'celery',
        '-A', 'docs_metadata_enhancer',
        'worker',
        '-l', 'info',
        '--pool=solo',
        '--concurrency=1',
        '--without-gossip',
        '--without-mingle',
        '--hostname=celery@%h'
    ]
    
    try:
        celery_process = subprocess.Popen(
            celery_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        CELERY_PROCESS = celery_process

        # Функция для чтения и логирования вывода
        def log_output(process, name, startup_messages):
            startup_timeout = 10  # Увеличенное время ожидания стартовых сообщений (в секундах)
            start_time = time.time()
            while time.time() - start_time < startup_timeout:
                if process.poll() is not None:
                    print(f"Процесс {name} завершился с кодом {process.returncode}")
                    return False  # Процесс завершился с ошибкой
                
                line = process.stderr.readline()
                if line:
                    print(f"[{name} ERROR] {line.strip()}")
                    startup_messages.append(line)
                line = process.stdout.readline()
                if line:
                    print(f"[{name}] {line.strip()}")
                    startup_messages.append(line)
                if "ready" in ''.join(startup_messages).lower():
                    return True  # Процесс успешно запустился
                
                time.sleep(0.1)
            return False  # Тайм-аут, процесс не запустился

        # Список для хранения сообщений
        celery_messages = []

        # Запускаем логирование и проверку статуса
        celery_thread = threading.Thread(
            target=log_output, args=(celery_process, "Celery Worker", celery_messages), daemon=True
        )
        celery_thread.start()
        celery_thread.join(timeout=11)  # Увеличенный таймаут для проверки запуска

        # Проверяем, запустился ли worker
        celery_running = "ready" in ''.join(celery_messages).lower()
        if celery_running:
            print("Celery Worker успешно запущен")
        else:
            print("Ошибка: Celery Worker не удалось запустить. Проверьте логи и настройки Redis.")
            print("Django будет работать без возможности фоновой обработки задач.")
            for msg in celery_messages:
                print(f"[Celery Worker Log] {msg.strip()}")
            
            # Останавливаем неудачно запущенный процесс
            if celery_process and celery_process.poll() is None:
                celery_process.terminate()
                try:
                    celery_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    celery_process.kill()
                CELERY_PROCESS = None
                CELERY_STARTED = False
                return None

        # Фоновое логирование
        def continuous_log_output(process, name):
            while process and process.poll() is None:
                line = process.stdout.readline()
                if line:
                    print(f"[{name}] {line.strip()}")
                line = process.stderr.readline()
                if line:
                    print(f"[{name} ERROR] {line.strip()}")
                time.sleep(0.1)

        threading.Thread(target=continuous_log_output, args=(celery_process, "Celery Worker"), daemon=True).start()

        return celery_process
    except Exception as e:
        print(f"Ошибка при запуске Celery: {str(e)}")
        CELERY_STARTED = False
        return None

def stop_celery(celery_process):
    """Корректно останавливает Celery worker."""
    if not celery_process:
        return
        
    print("Останавливаем Celery процесс...")
    
    # Сначала посылаем SIGTERM для корректного завершения
    celery_process.terminate()
    
    # Даем процессу время на корректное завершение
    try:
        celery_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # Если процесс не завершился за отведенное время, используем SIGKILL
        print("Celery не завершился корректно, принудительное завершение...")
        celery_process.kill()
        celery_process.wait()
    
    print("Celery процесс остановлен")

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'docs_metadata_enhancer.settings')
    
    try:
        if 'runserver' in sys.argv:
            # Запускаем Celery, но продолжаем даже если не удалось
            celery_process = start_celery()
            
            # Обработчик сигналов для корректного завершения
            def signal_handler(sig, frame):
                print("Получен сигнал завершения, останавливаем сервисы...")
                stop_celery(celery_process)
                sys.exit(0)
                
            # Регистрируем обработчик для SIGINT (Ctrl+C) и SIGTERM
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            try:
                execute_from_command_line(sys.argv)
            except KeyboardInterrupt:
                print("Прерывание выполнения пользователем...")
                stop_celery(celery_process)
                sys.exit(0)
        else:
            execute_from_command_line(sys.argv)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()