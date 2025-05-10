#!/usr/bin/env python
"""
Утилиты для диагностики и проверки системных зависимостей проекта.
"""
import os
import sys
import platform
import subprocess
import socket
import logging
import time
import json
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Пути к логам для сохранения результатов
LOG_DIR = Path(__file__).resolve().parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

def check_redis():
    """Проверяет доступность Redis."""
    logger.info("=== Проверка Redis ===")
    
    # Настройки Redis из settings
    try:
        # Импортируем настройки Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'docs_metadata_enhancer.settings')
        import django
        django.setup()
        
        from django.conf import settings
        host = getattr(settings, 'REDIS_HOST', 'localhost')
        port = int(getattr(settings, 'REDIS_PORT', 6379))
        password = getattr(settings, 'REDIS_PASSWORD', None)
        
        try:
            import redis
            logger.info(f"Проверка подключения к Redis по адресу {host}:{port}...")
            r = redis.Redis(
                host=host,
                port=port,
                password=password,
                socket_timeout=2
            )
            ping_result = r.ping()
            
            if ping_result:
                logger.info(f"✅ Redis доступен по адресу {host}:{port}")
                r.set('test_key', 'test_value', ex=60)
                get_result = r.get('test_key')
                logger.info(f"✅ Тест записи/чтения данных: {get_result.decode() if get_result else None}")
                return True
            else:
                logger.error(f"❌ Redis не ответил на PING")
                return False
                
        except redis.exceptions.ConnectionError as e:
            logger.error(f"❌ Не удалось подключиться к Redis: {str(e)}")
            return False
        except ImportError:
            logger.error("❌ Модуль redis не установлен. Установите его командой: pip install redis")
            return False
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка при подключении к Redis: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при получении настроек Redis: {str(e)}")
        return False

def check_docker():
    """Проверяет доступность Docker."""
    logger.info("=== Проверка Docker ===")
    
    if platform.system() == 'Windows':
        logger.info("Система: Windows")
        docker_cmd = 'docker'
    else:
        logger.info(f"Система: {platform.system()}")
        docker_cmd = 'docker'
    
    try:
        # Проверка версии Docker
        version_result = subprocess.run(
            [docker_cmd, '--version'], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        if version_result.returncode == 0:
            logger.info(f"✅ Docker установлен: {version_result.stdout.strip()}")
        else:
            logger.error(f"❌ Docker не установлен или не доступен. Ошибка: {version_result.stderr}")
            return False
        
        # Проверка работы Docker
        ps_result = subprocess.run(
            [docker_cmd, 'ps'], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        if ps_result.returncode == 0:
            logger.info("✅ Docker daemon работает")
            
            # Поиск контейнера Redis
            redis_containers = subprocess.run(
                [docker_cmd, 'ps', '-a', '--filter', 'name=redis', '--format', '{{json .}}'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            
            if redis_containers.returncode == 0 and redis_containers.stdout.strip():
                for line in redis_containers.stdout.strip().split('\n'):
                    if line:
                        container = json.loads(line)
                        logger.info(f"Найден контейнер Redis: {container.get('Names')} (Статус: {container.get('Status')})")
                        
                        # Если контейнер остановлен, пробуем запустить
                        if not container.get('Status', '').startswith('Up'):
                            logger.info(f"Попытка запустить контейнер {container.get('Names')}...")
                            start_result = subprocess.run(
                                [docker_cmd, 'start', container.get('Names')], 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.PIPE,
                                text=True,
                                check=False
                            )
                            
                            if start_result.returncode == 0:
                                logger.info(f"✅ Контейнер {container.get('Names')} успешно запущен")
                                # Ждем немного чтобы Redis успел подняться
                                time.sleep(3)
                                # Проверяем подключение
                                if check_redis():
                                    logger.info(f"✅ Redis успешно запущен в контейнере {container.get('Names')}")
                                else:
                                    logger.warning(f"⚠️ Redis запущен, но не отвечает на запросы")
                            else:
                                logger.error(f"❌ Не удалось запустить контейнер: {start_result.stderr}")
            else:
                logger.warning("⚠️ Не найдены контейнеры Redis")
                logger.info("Рекомендация: Запустите Redis в Docker контейнере:")
                logger.info("docker run --name redis -p 6379:6379 -d redis:latest redis-server --requirepass 12345678")
        
        else:
            logger.error(f"❌ Docker daemon не работает. Ошибка: {ps_result.stderr}")
            return False
            
        return True
        
    except FileNotFoundError:
        logger.error("❌ Docker не установлен или не найден в PATH")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке Docker: {str(e)}")
        return False

def check_celery():
    """Проверяет настройки и зависимости Celery."""
    logger.info("=== Проверка Celery ===")
    
    try:
        import celery
        logger.info(f"✅ Celery установлен: версия {celery.__version__}")
        
        # Проверка доступности Django settings
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'docs_metadata_enhancer.settings')
        import django
        django.setup()
        
        # Импортируем Celery app
        try:
            from docs_metadata_enhancer.celery import app as celery_app
            logger.info(f"✅ Celery app загружена: {celery_app}")
            
            # Проверка настроек
            broker_url = celery_app.conf.broker_url
            result_backend = celery_app.conf.result_backend
            logger.info(f"Celery broker URL: {broker_url}")
            logger.info(f"Celery result backend: {result_backend}")
            
            # Проверка задач
            tasks = list(celery_app.tasks.keys())
            logger.info(f"Найдено {len(tasks)} задач:")
            for task in sorted(tasks):
                if not task.startswith('celery.'):
                    logger.info(f"  - {task}")
            
            # Проверка eager mode
            if celery_app.conf.task_always_eager:
                logger.warning("⚠️ Celery работает в eager режиме - задачи будут выполняться синхронно!")
            
            return True
        except ImportError:
            logger.error("❌ Не удалось импортировать Celery app из проекта")
            return False
        
    except ImportError:
        logger.error("❌ Celery не установлен. Установите его командой: pip install celery")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке Celery: {str(e)}")
        return False

def run_all_checks():
    """Запускает все проверки системы."""
    checks = [
        ("Docker", check_docker), 
        ("Redis", check_redis),
        ("Celery", check_celery)
    ]
    
    results = {}
    success_count = 0
    
    logger.info("====== Начало диагностики системы ======")
    logger.info(f"Время запуска: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Система: {platform.system()} {platform.release()}")
    logger.info(f"Python: {platform.python_version()}")
    
    # Создаем отдельный log файл для текущей проверки
    log_file = LOG_DIR / f"system_check_{time.strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    for name, check_func in checks:
        logger.info(f"\n\n========== Проверка: {name} ==========")
        try:
            result = check_func()
            results[name] = result
            if result:
                success_count += 1
                logger.info(f"✅ Проверка {name}: УСПЕШНО")
            else:
                logger.error(f"❌ Проверка {name}: НЕУДАЧА")
        except Exception as e:
            results[name] = False
            logger.error(f"❌ Ошибка при выполнении проверки {name}: {str(e)}")
    
    logger.info("\n\n====== Результат диагностики системы ======")
    for name, result in results.items():
        status = "✅ УСПЕШНО" if result else "❌ НЕУДАЧА"
        logger.info(f"{name}: {status}")
    
    logger.info(f"Итог: {success_count}/{len(checks)} проверок пройдено успешно")
    
    if success_count < len(checks):
        logger.info("\nРекомендации по исправлению:")
        if not results.get("Docker", False):
            logger.info("1. Проверьте, что Docker установлен и запущен")
            logger.info("   - Windows: Запустите Docker Desktop")
            logger.info("   - Linux: sudo systemctl start docker")
        
        if not results.get("Redis", False):
            logger.info("\n2. Запустите Redis:")
            logger.info("   - В Docker: docker run --name redis -p 6379:6379 -d redis:latest redis-server --requirepass 12345678")
            logger.info("   - Или установите Redis локально")
        
        if not results.get("Celery", False):
            logger.info("\n3. Проверьте настройки Celery:")
            logger.info("   - Установите зависимости: pip install celery redis")
            logger.info("   - Проверьте настройки в файле docs_metadata_enhancer/settings.py")
    
    logger.info(f"\nЛог сохранен в: {log_file}")
    logger.removeHandler(file_handler)
    
    return results

if __name__ == "__main__":
    results = run_all_checks()
    # Возвращаем код завершения 0, если все проверки успешны, иначе 1
    sys.exit(0 if all(results.values()) else 1)