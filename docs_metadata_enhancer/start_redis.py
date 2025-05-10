#!/usr/bin/env python
"""
Скрипт для запуска Redis в Docker.
Проверяет наличие контейнера Redis и при необходимости создает его.
"""
import os
import sys
import subprocess
import time
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Получаем настройки Redis из Django settings
def get_redis_settings():
    try:
        # Настраиваем окружение для Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'docs_metadata_enhancer.settings')
        import django
        django.setup()
        
        # Импортируем настройки
        from django.conf import settings
        redis_host = getattr(settings, 'REDIS_HOST', 'localhost')
        redis_port = int(getattr(settings, 'REDIS_PORT', 6379))
        redis_password = getattr(settings, 'REDIS_PASSWORD', '12345678')
        
        return redis_host, redis_port, redis_password
    except Exception as e:
        logger.error(f"Ошибка при получении настроек Redis: {e}")
        return 'localhost', 6379, '12345678'

# Проверяет наличие и состояние контейнера Redis
def check_redis_container():
    try:
        # Проверяем, есть ли контейнер Redis
        result = subprocess.run(
            ['docker', 'ps', '-a', '--filter', 'name=redis', '--format', '{{.Names}} {{.Status}}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
        )
        
        # Если команда выполнена успешно и найден контейнер
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n'):
                parts = line.split(' ')
                if len(parts) >= 2:
                    container_name = parts[0]
                    status = ' '.join(parts[1:])
                    
                    if status.startswith('Up'):
                        logger.info(f"Контейнер Redis '{container_name}' уже запущен")
                        return True, container_name
                    else:
                        logger.info(f"Контейнер Redis '{container_name}' существует, но не запущен (статус: {status})")
                        return False, container_name
        
        logger.info("Контейнер Redis не найден")
        return False, None
        
    except Exception as e:
        logger.error(f"Ошибка при проверке контейнера Redis: {e}")
        return False, None

# Запускает существующий контейнер Redis
def start_redis_container(container_name):
    try:
        logger.info(f"Запуск контейнера Redis '{container_name}'...")
        
        result = subprocess.run(
            ['docker', 'start', container_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
        )
        
        if result.returncode == 0:
            logger.info(f"Контейнер Redis '{container_name}' успешно запущен")
            return True
        else:
            logger.error(f"Ошибка при запуске контейнера Redis: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при запуске контейнера Redis: {e}")
        return False

# Создает и запускает новый контейнер Redis
def create_redis_container(host, port, password):
    try:
        container_name = 'redis'
        logger.info(f"Создание нового контейнера Redis '{container_name}'...")
        
        # Проверяем, есть ли образ Redis
        image_result = subprocess.run(
            ['docker', 'images', 'redis', '--format', '{{.Repository}}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
        )
        
        if image_result.returncode != 0 or not image_result.stdout.strip():
            logger.info("Образ Redis не найден, загружаем...")
            pull_result = subprocess.run(
                ['docker', 'pull', 'redis:latest'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
            )
            
            if pull_result.returncode != 0:
                logger.error(f"Ошибка при загрузке образа Redis: {pull_result.stderr}")
                return False
        
        # Создаем контейнер
        result = subprocess.run(
            [
                'docker', 'run', '--name', container_name, 
                '-p', f'{port}:{port}', 
                '-d', 'redis:latest', 
                'redis-server', f'--requirepass', password
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
        )
        
        if result.returncode == 0:
            logger.info(f"Контейнер Redis '{container_name}' успешно создан и запущен")
            return True
        else:
            logger.error(f"Ошибка при создании контейнера Redis: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при создании контейнера Redis: {e}")
        return False

# Проверяет работу Redis
def test_redis_connection(host, port, password):
    try:
        import redis
        logger.info(f"Проверка подключения к Redis ({host}:{port})...")
        
        # Создаем клиент Redis
        r = redis.Redis(
            host=host,
            port=port,
            password=password,
            socket_timeout=3
        )
        
        # Пингуем Redis
        if r.ping():
            logger.info("Соединение с Redis установлено успешно")
            
            # Тестируем запись/чтение данных
            test_key = "test_key"
            test_value = "test_value"
            r.set(test_key, test_value, ex=10)  # Устанавливаем с истечением через 10 секунд
            
            retrieved_value = r.get(test_key)
            if retrieved_value and retrieved_value.decode() == test_value:
                logger.info(f"Тест записи/чтения успешен: {test_key}={retrieved_value.decode()}")
                return True
            else:
                logger.error(f"Тест записи/чтения не удался: {test_key}={retrieved_value}")
                return False
        else:
            logger.error("Redis не ответил на ping")
            return False
            
    except ImportError:
        logger.error("Модуль redis не установлен. Установите его: pip install redis")
        return False
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Ошибка подключения к Redis: {e}")
        return False
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при проверке Redis: {e}")
        return False

def main():
    """Основная функция для запуска Redis."""
    logger.info("=== Запуск Redis для проекта docs_metadata_enhancer ===")
    
    # Получаем настройки Redis из Django
    host, port, password = get_redis_settings()
    logger.info(f"Настройки Redis: host={host}, port={port}")
    
    # Проверяем Docker
    docker_result = subprocess.run(
        ['docker', 'version'], 
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False
    )
    
    if docker_result.returncode != 0:
        logger.error("Docker не запущен или не установлен. Пожалуйста, убедитесь, что Docker запущен.")
        return False
    
    # Проверяем наличие контейнера Redis
    container_running, container_name = check_redis_container()
    
    if container_running:
        # Контейнер уже запущен
        pass
    elif container_name:
        # Контейнер существует, но не запущен
        if not start_redis_container(container_name):
            return False
    else:
        # Контейнер не существует, создаем новый
        if not create_redis_container(host, port, password):
            return False
    
    # Даем Redis время на инициализацию
    logger.info("Ожидание 3 секунды для инициализации Redis...")
    time.sleep(3)
    
    # Проверяем работу Redis
    if test_redis_connection(host, port, password):
        logger.info("=== Redis успешно запущен и готов к использованию ===")
        return True
    else:
        logger.error("=== Не удалось подключиться к Redis после запуска ===")
        logger.info("Проверьте настройки Redis в файле settings.py:")
        logger.info(f"REDIS_HOST = '{host}'")
        logger.info(f"REDIS_PORT = '{port}'")
        logger.info(f"REDIS_PASSWORD = '********'")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 