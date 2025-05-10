import logging
import time
import traceback
from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.exceptions import ObjectDoesNotExist
from django import db
from celery import current_app

from apps.enhancer.processing.pipeline import (
    process_doc_pipeline, process_wikidata_pipeline)

from .models import Document

# Используем специальный логгер задач Celery для лучшей интеграции
logger = get_task_logger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def process_document(self, document_id):
    """Задача для обработки загруженного документа.
    
    Извлекает сущности из документа и обогащает их данными из Wikidata.
    Аргументы:
        document_id (int): ID документа для обработки
    """
    # Определяем, запущена ли задача в eager режиме (синхронное выполнение без Celery)
    is_eager = getattr(current_app.conf, 'task_always_eager', False)
    task_id = getattr(self.request, 'id', 'sync-mode') if not is_eager else 'direct-mode'
    
    logger.info(f"[Задача {task_id}] Запущена обработка документа с ID {document_id} (режим: {'eager' if is_eager else 'async'})")
    
    # В Django, при длительных фоновых задачах может произойти разрыв соединения с БД
    # Закрываем и пересоздаем соединение для долгих операций
    db.close_old_connections()
    
    start_time = time.time()
    try:
        # Получение документа из БД
        document = Document.objects.get(id=document_id)
        logger.info(f"[Задача {task_id}] Начало обработки документа '{document.name}' (ID: {document_id})")
        
        # Обновление статуса документа
        document.processing_status = 'processing'
        document.save(update_fields=['processing_status'])
        
        # Шаг 1: Извлечение сущностей из документа
        logger.info(f"[Задача {task_id}] Извлечение сущностей из документа...")
        try:
            final_entities = process_doc_pipeline(document.file.path, 3000, 200)
            if not final_entities:
                document.processing_status = 'failed'
                document.processing_errors = "Не удалось извлечь сущности из документа"
                document.save(update_fields=['processing_status', 'processing_errors'])
                logger.error(f"[Задача {task_id}] Не удалось извлечь сущности для документа '{document.name}'")
                return False
            document.metadata = final_entities
            document.save(update_fields=['metadata'])
        except Exception as e:
            error_msg = f"Ошибка при извлечении сущностей: {str(e)}"
            document.processing_status = 'failed'
            document.processing_errors = error_msg
            document.save(update_fields=['processing_status', 'processing_errors'])
            logger.error(f"[Задача {task_id}] {error_msg}")
            logger.error(traceback.format_exc())
            return False
            
        # Успешное завершение обработки
        document.processing_status = 'success'
        document.processing_errors = None
        document.save(update_fields=['processing_status', 'processing_errors'])
        
        elapsed_time = time.time() - start_time
        logger.info(f"[Задача {task_id}] Документ '{document.name}' успешно обработан за {elapsed_time:.2f} сек.")
        return True
    
    except ObjectDoesNotExist:
        logger.error(f"[Задача {task_id}] Документ с ID {document_id} не найден в базе данных")
        return False
    
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"[Задача {task_id}] Ошибка при обработке документа {document_id} (время: {elapsed_time:.2f} сек): {str(e)}")
        logger.error(f"[Задача {task_id}] Трассировка: {traceback.format_exc()}")
        
        # Обновляем статус документа, если он существует
        if 'document' in locals():
            document.processing_status = 'failed'
            document.processing_errors = f"Непредвиденная ошибка: {str(e)}"
            document.save(update_fields=['processing_status', 'processing_errors'])
        
        # Пробуем повторить выполнение задачи, если это не последняя попытка
        if hasattr(self, 'request') and hasattr(self.request, 'retries') and self.request.retries < self.max_retries:
            logger.info(f"[Задача {task_id}] Повторная попытка обработки документа {document_id} ({self.request.retries + 1}/{self.max_retries + 1})")
        
        # Передаем исключение дальше для автоматического повтора задачи
        raise
    finally:
        # Закрываем соединения с БД в конце задачи
        db.close_old_connections()
