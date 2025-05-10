import json
import logging
import traceback
from collections import defaultdict

from apps.enhancer.LLM.sber.giga_chat import finalize_entities, process_text_with_gigachat
from apps.enhancer.processing.pre_processing import split_text

# Настройка логирования
logger = logging.getLogger(__name__)
 
def merge_entities(entities_list):
    """
    Объединяет сущности из списка без удаления дубликатов.
    Args:
        entities_list (list): Список словарей с сущностями
    Returns:
        dict: Объединённые сущности
    """
    try:
        logger.info(f"Начало объединения сущностей из {len(entities_list)} источников")
        
        merged = {
            "creator": [],
            "organizations": [],
            "title": [],
            "keywords": [],
            "dates": [],
            "summary": [],
            "subject": [],
            "document_language": [],
            "identifier": [],
            "contributor": [],
            "rights": []
        }
        
        for i, entities in enumerate(entities_list):
            if not entities:
                logger.warning(f"Источник #{i+1} не содержит сущностей, пропускаем")
                continue
                
            logger.info(f"Обработка источника #{i+1}. Найденные ключи: {list(entities.keys())}")
            merged["creator"].extend(entities.get("creator", []))
            merged["organizations"].extend(entities.get("organizations", []))
            merged["keywords"].extend(entities.get("keywords", []))
            merged["dates"].extend(entities.get("dates", []))
            merged["subject"].extend(entities.get("subject", []))
            merged["contributor"].extend(entities.get("contributor", []))
            if entities.get("title"):
                merged["title"].append(entities["title"])
            if entities.get("summary"):
                merged["summary"].append(entities["summary"])
            if entities.get("document_language"):
                merged["document_language"].append(entities["document_language"])
            if entities.get("identifier"):
                merged["identifier"].append(entities["identifier"])
            if entities.get("rights"):
                merged["rights"].append(entities["rights"])
        
        # Логирование статистики по объединенным сущностям
        stats = {key: len(value) for key, value in merged.items()}
        logger.info(f"Объединение сущностей завершено: {stats}")
        
        return merged
    except Exception as e:
        logger.error(f"Ошибка при объединении сущностей: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None


def extract_and_finalize_entities(text, chunk_size=1000, chunk_overlap=200):
    """
    Разбивает текст на чанки, извлекает сущности с помощью GigaChat и выполняет финальную обработку.
    Args:
        final_text (str): Текст для обработки
        chunk_size (int): Размер чанка (по умолчанию 1000 символов)
        chunk_overlap (int): Перекрытие между чанками (по умолчанию 200 символов)
    Returns:
        dict: Финальный JSON с обработанными сущностями или None в случае ошибки
    """
    try:
        logger.info(f"Начало извлечения сущностей из текста длиной {len(text)} символов")
        logger.info(f"Параметры: chunk_size={chunk_size}, chunk_overlap={chunk_overlap}")
        
        # Разбиваем текст на чанки
        chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        logger.info(f"Текст разбит на {len(chunks)} чанков")
        
        # Обрабатываем каждый чанк с GigaChat
        entities_list = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Обработка чанка {i+1}/{len(chunks)}, длина чанка: {len(chunk)} символов")
            
            try:
                entities = process_text_with_gigachat(chunk)
                if entities:
                    logger.info(f"Чанк {i+1}: успешно извлечены сущности - {list(entities.keys())}")
                    entities_list.append(entities)
                else:
                    logger.error(f"Чанк {i+1}: не удалось извлечь сущности")
            except Exception as chunk_error:
                logger.error(f"Ошибка при обработке чанка {i+1}: {str(chunk_error)}")
                logger.error(traceback.format_exc())
        
        logger.info(f"Обработано {len(entities_list)}/{len(chunks)} чанков")
        
        if not entities_list:
            logger.error("Все чанки обработаны с ошибкой, нет данных для объединения")
            return None
            
        # Объединяем сущности
        logger.info("Объединение сущностей из всех чанков")
        merged_entities = merge_entities(entities_list)
        if not merged_entities:
            logger.error("Не удалось объединить сущности")
            return None
            
        # Финальная обработка сущностей
        logger.info("Финальная обработка сущностей с помощью GigaChat")
        try:
            final_entities = finalize_entities(merged_entities)
            if not final_entities:
                logger.error("Не удалось выполнить финальную обработку сущностей")
                return None
            logger.info(f"Финальная обработка завершена успешно. Итоговые сущности: {list(final_entities.keys())}")
            return final_entities
        except Exception as finalize_error:
            logger.error(f"Ошибка при финальной обработке сущностей: {str(finalize_error)}")
            logger.error(traceback.format_exc())
            return None
    
    except Exception as e:
        logger.error(f"Ошибка при извлечении и финализации сущностей: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None
    
    
