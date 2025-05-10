"""
Пайплайн для обработки документов: загрузка, предобработка текста,
извлечение и финализация сущностей с использованием GigaChat.
"""

import json
import logging
import traceback
from apps.enhancer.models import Document
from apps.enhancer.processing.pre_processing import load_and_combine_pdf, preprocess_text
from apps.enhancer.processing.post_processing import extract_and_finalize_entities
from apps.enhancer.processing.wikidata import enrich_with_wikidata

# Настройка логирования
logger = logging.getLogger(__name__)

def process_doc_pipeline(doc_path, chunk_size=3000, chunk_overlap=200):
    """
    Пайплайн для обработки PDF: загрузка, предобработка, извлечение и финализация сущностей.
    Args:
        pdf_path (str): Путь к PDF-файлу
        chunk_size (int): Размер чанка (по умолчанию 1000 символов)
        chunk_overlap (int): Перекрытие между чанками (по умолчанию 200 символов)
    Returns:
        dict: Финальный JSON с обработанными сущностями или None в случае ошибки
    """
    try:
        logger.info(f"Начало обработки документа: {doc_path}")
        
        # Шаг 1: Загрузка и объединение текста из PDF
        logger.info("Шаг 1: Загрузка и объединение текста из документа")
        full_text = load_and_combine_pdf(doc_path)
        if not full_text:
            logger.error("Ошибка: не удалось загрузить и объединить текст из документа")
            return None
        logger.info(f"Документ успешно загружен, получено {len(full_text)} символов текста")

        # Шаг 2: Предобработка текста
        logger.info("Шаг 2: Предобработка текста")
        final_text = preprocess_text(full_text)
        if not final_text:
            logger.error("Ошибка: не удалось выполнить предобработку текста")
            return None
        logger.info(f"Предобработка завершена, получено {len(final_text)} символов текста после обработки")

        # Шаг 3: Извлечение и финализация сущностей
        logger.info("Шаг 3: Извлечение и финализация сущностей")
        final_entities = extract_and_finalize_entities(final_text, chunk_size, chunk_overlap)
        if not final_entities:
            logger.error("Ошибка: не удалось извлечь сущности")
            return None
        
        logger.info(f"Обработка документа успешно завершена. Извлечены сущности: {list(final_entities.keys())}")
        return final_entities

    except Exception as e:
        logger.error(f"Ошибка в пайплайне обработки документа: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None
    
def process_wikidata_pipeline(final_entities, document):
    """
    Пайплайн для обогащения сущностей документа данными из Wikidata и сохранения в базе данных.
    Args:
        final_entities (dict): Извлечённые сущности в формате JSON
        document (Document): Объект документа Django
    Returns:
        dict: Обогащённый JSON с Q-идентификаторами Wikidata или None в случае ошибки
    """
    try:
        logger.info(f"Начало обогащения сущностей Wikidata для документа ID: {document.id}")
        
        if not final_entities:
            logger.error("Ошибка: входные сущности пусты")
            return None
        
        if not isinstance(document, Document):
            logger.error("Ошибка: передан некорректный объект документа")
            return None

        # Обогащаем сущности данными Wikidata и создаём связи в базе данных
        logger.info(f"Обогащение сущностей данными Wikidata. Входные сущности: {list(final_entities.keys())}")
        enriched_entities = enrich_with_wikidata(final_entities, document)
        if not enriched_entities:
            logger.error("Ошибка: не удалось обогатить сущности Wikidata")
            return None

        logger.info(f"Обогащение сущностей Wikidata успешно завершено")
        return enriched_entities

    except Exception as e:
        logger.error(f"Ошибка в пайплайне обогащения Wikidata: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None
    
