# apps/enhancer/management/commands/runserver.py
import os
import subprocess
import sys
import threading
import time
from django.core.management.commands.runserver import Command as RunserverCommand

class Command(RunserverCommand):
    def handle(self, *args, **options):
        print("Запуск Celery процессов...")

        # Запускаем Celery worker
        celery_command = ['celery', '-A', 'docs_metadata_enhancer', 'worker', '-l', 'info']
        celery_process = subprocess.Popen(
            celery_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Запускаем Celery beat
        beat_command = ['celery', '-A', 'docs_metadata_enhancer', 'beat', '-l', 'info']
        beat_process = subprocess.Popen(
            beat_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Функция для чтения и логирования вывода процессов
        def log_output(process, name, startup_messages):
            startup_timeout = 5  # Время ожидания стартовых сообщений (в секундах)
            start_time = time.time()
            while time.time() - start_time < startup_timeout:
                line = process.stderr.readline()
                if line:
                    print(f"[{name} ERROR] {line.strip()}")
                    startup_messages.append(line)
                line = process.stdout.readline()
                if line:
                    print(f"[{name}] {line.strip()}")
                    startup_messages.append(line)
                    if "ready" in line.lower() or "scheduler" in line.lower():
                        return True  # Процесс успешно запустился
                if process.poll() is not None:
                    return False  # Процесс завершился с ошибкой
                time.sleep(0.1)
            return False  # Тайм-аут, процесс не запустился

        # Список для хранения стартовых сообщений
        celery_messages = []
        beat_messages = []

        # Запускаем логирование и проверку статуса в отдельных потоках
        celery_thread = threading.Thread(
            target=log_output, args=(celery_process, "Celery Worker", celery_messages), daemon=True
        )
        beat_thread = threading.Thread(
            target=log_output, args=(beat_process, "Celery Beat", beat_messages), daemon=True
        )
        celery_thread.start()
        beat_thread.start()

        # Ждём завершения проверки статуса
        celery_thread.join(timeout=6)
        beat_thread.join(timeout=6)

        # Проверяем, запустились ли процессы
        celery_running = any("ready" in msg.lower() for msg in celery_messages)
        beat_running = any("scheduler" in msg.lower() for msg in beat_messages)

        # Выводим статус в консоль
        if celery_running:
            print("Celery Worker успешно запущен")
        else:
            print("Ошибка: Celery Worker не удалось запустить. Проверьте логи и настройки Redis.")
            for msg in celery_messages:
                print(f"[Celery Worker Log] {msg.strip()}")

        if beat_running:
            print("Celery Beat успешно запущен")
        else:
            print("Ошибка: Celery Beat не удалось запустить. Проверьте логи и настройки Redis.")
            for msg in beat_messages:
                print(f"[Celery Beat Log] {msg.strip()}")

        # Продолжаем логирование вывода в фоновом режиме
        def continuous_log_output(process, name):
            for line in iter(process.stdout.readline, ''):
                print(f"[{name}] {line.strip()}")
            for line in iter(process.stderr.readline, ''):
                print(f"[{name} ERROR] {line.strip()}")

        threading.Thread(target=continuous_log_output, args=(celery_process, "Celery Worker"), daemon=True).start()
        threading.Thread(target=continuous_log_output, args=(beat_process, "Celery Beat"), daemon=True).start()

        try:
            # Запускаем Django сервер
            super().handle(*args, **options)
        except KeyboardInterrupt:
            print("Останавливаем Celery процессы...")
            celery_process.terminate()
            beat_process.terminate()
            celery_process.wait()
            beat_process.wait()
            sys.exit(0)