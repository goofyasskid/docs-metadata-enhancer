import time
import logging
import requests
from requests.exceptions import RequestException

from apps.enhancer.models import Document
from apps.enhancer.processing.wikidata_orm import enrich_entity_with_wikidata

# Получение логгера
logger = logging.getLogger(__name__)

# Глобальный кэш для результатов Wikidata
wikidata_cache = {}

# Кэш для сущностей, которые не удалось найти из-за проблем с сетью
network_failure_cache = {}
# Кэш известных сопоставлений (можно использовать при проблемах с сетью)
known_entities = {
    # "Ленин": "Q1394",  # Владимир Ленин
}

# Список основных полей метаданных, для которых нужно применять фильтр по типу
CORE_METADATA_FIELDS = [
    "creator", "organizations", "title", "keywords", "dates", "summary", 
    "subject", "document_language", "identifier", "contributor", "rights"
]

def test_wikidata_connection():
    """
    Проверяет соединение с Wikidata API.
    Returns:
        bool: True, если соединение работает, иначе False
    """
    logger.info("Проверка соединения с Wikidata...")
    headers = {
        "User-Agent": "DocsMetadataEnhancerBot/1.0 (https://example.com; zheny@example.com)"
    }
    try:
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "search": "test",
            "language": "ru",
            "format": "json",
            "limit": 1
        }
        
        response = requests.get(search_url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if "search" in data:
            logger.info("Соединение с Wikidata работает")
            return True
        
        logger.warning("Нестандартный ответ от Wikidata API")
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке соединения с Wikidata: {str(e)}")
        return False

def link_to_wikidata(entity_name, entity_type=None):
    """
    Связывает сущность с Wikidata, возвращая только Q-идентификатор.
    Args:
        entity_name (str): Название сущности (например, "Университет Джорджии")
        entity_type (str): Тип сущности (person, organization, concept, language, discipline)
    Returns:
        str: Q-идентификатор (например, "Q123") или None
    """
    if not entity_name or not isinstance(entity_name, str):
        logger.warning(f"Попытка связать пустую или невалидную строку с Wikidata: '{entity_name}'")
        return None
        
    entity_name = entity_name.strip()
    if not entity_name:
        logger.warning("Попытка связать пустую строку с Wikidata")
        return None
        
    # Проверяем кэш
    cache_key = f"{entity_name}:{entity_type}"
    if cache_key in wikidata_cache:
        logger.debug(f"Найдено в кэше: {entity_name} -> {wikidata_cache[cache_key]}")
        return wikidata_cache[cache_key]
    
    # Проверяем кэш известных сущностей
    if entity_name in known_entities:
        logger.info(f"Найдено в локальном кэше: {entity_name} -> {known_entities[entity_name]}")
        wikidata_cache[cache_key] = known_entities[entity_name]
        return known_entities[entity_name]
    
    # Проверяем кэш ошибок сети
    if cache_key in network_failure_cache:
        logger.warning(f"Пропускаем запрос к Wikidata из-за предыдущей ошибки сети: {entity_name}")
        return None

    logger.info(f"Поиск сущности в Wikidata: '{entity_name}' (тип: {entity_type})")
    
    headers = {
        "User-Agent": "DocsMetadataEnhancerBot/1.0 (https://example.com; zheny@example.com)"
    }

    try:
        # Шаг 1: Поиск через wbsearchentities
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "search": entity_name,
            "language": "ru",
            "uselang": "ru",
            "format": "json",
            "limit": 10
        }
        
        logger.debug(f"Отправка запроса на поиск: {search_url} с параметрами {params}")
        
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        search_results = response.json().get("search", [])

        # Если ничего не найдено, пробуем на английском
        if not search_results:
            logger.debug(f"Ничего не найдено на русском, пробуем на английском: '{entity_name}'")
            params["language"] = "en"
            params["uselang"] = "en"
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            search_results = response.json().get("search", [])

        if not search_results:
            logger.info(f"Сущность не найдена в Wikidata: '{entity_name}'")
            wikidata_cache[cache_key] = None
            return None

        # Фильтрация по типу сущности
        valid_types = {
            "person": ["Q5"],  # человек
            "organization": ["Q43229", "Q3918", "Q875538"],  # организация, университет
            "language": ["Q34770"],  # язык
            "discipline": ["Q11862829"],  # академическая дисциплина
            "concept": ["Q1656682", "Q7184903"]  # концепция или абстрактное понятие
        }
        best_result = None
        
        # Применяем фильтрацию по типу только для основных полей
        # Для всех остальных полей берем лучший результат по совпадению метки
        if entity_type and entity_type in valid_types:
            logger.debug(f"Фильтрация по типу: {entity_type} для '{entity_name}'")
            
            for result in search_results:
                entity_id = result["id"]
                # Проверяем тип через SPARQL
                sparql_query = f"""
                SELECT ?type WHERE {{
                    wd:{entity_id} wdt:P31 ?type .
                }}
                """
                sparql_url = "https://query.wikidata.org/sparql"
                sparql_params = {"query": sparql_query, "format": "json"}
                
                try:
                    time.sleep(0.5)  # Задержка для соблюдения лимитов
                    logger.debug(f"SPARQL запрос для {entity_id}: {sparql_query}")
                    
                    sparql_response = requests.get(sparql_url, params=sparql_params, headers=headers, timeout=15)
                    sparql_response.raise_for_status()
                    
                    types = [binding["type"]["value"].split("/")[-1] for binding in sparql_response.json().get("results", {}).get("bindings", [])]
                    
                    logger.debug(f"Типы для {entity_id}: {types}")
                    
                    if any(t in valid_types[entity_type] for t in types):
                        logger.info(f"Найдена подходящая сущность типа {entity_type} для '{entity_name}': {entity_id}")
                        best_result = result
                        break
                except Exception as sparql_error:
                    logger.warning(f"Ошибка при выполнении SPARQL запроса для {entity_id}: {str(sparql_error)}")
                    continue
        else:
            # Берем первый результат, если тип не указан или не требуется фильтрация
            logger.debug(f"Тип не указан или не требует фильтрации, берем первый результат для '{entity_name}'")
            best_result = search_results[0]

        if not best_result:
            # Дополнительная попытка: ищем без строгой фильтрации, но с приоритетом по совпадению метки
            logger.debug(f"Поиск без строгой фильтрации для '{entity_name}'")
            
            for result in search_results:
                label = result.get("label", "").lower()
                if label == entity_name.lower():
                    logger.info(f"Найдено точное совпадение метки для '{entity_name}': {result['id']}")
                    best_result = result
                    break
            
            if not best_result:
                logger.info(f"Берем первый результат поиска для '{entity_name}': {search_results[0]['id']}")
                best_result = search_results[0]  # Берем первый, если нет точного совпадения

        entity_id = best_result["id"]
        logger.info(f"Финальный результат для '{entity_name}': {entity_id}")
        
        wikidata_cache[cache_key] = entity_id
        return entity_id

    except RequestException as e:
        logger.error(f"Ошибка при запросе к Wikidata для '{entity_name}': {str(e)}")
        # Добавляем в кэш ошибок сети
        network_failure_cache[cache_key] = True
        
        # Проверяем, есть ли известное соответствие в локальном кэше
        if entity_name in known_entities:
            logger.info(f"Использую локальный кэш из-за ошибки сети: {entity_name} -> {known_entities[entity_name]}")
            wikidata_cache[cache_key] = known_entities[entity_name]
            return known_entities[entity_name]
            
        wikidata_cache[cache_key] = None
        return None
    except Exception as e:
        logger.error(f"Общая ошибка при связывании '{entity_name}' с Wikidata: {str(e)}", exc_info=True)
        wikidata_cache[cache_key] = None
        return None
    
    
def enrich_with_wikidata(json_data, document):
    """
    Обогащает JSON данными из Wikidata, добавляя Q-идентификатор в поле wikidata,
    и создаёт связи в базе данных.
    Args:
        json_data (dict): Входной JSON с метаданными
        document (Document): Объект документа Django
    Returns:
        dict: JSON с добавленным полем wikidata, содержащим Q-идентификатор
    """
    enriched_data = json_data.copy()
    
    # Типы сущностей для каждого поля
    field_types = {
        "creator": "person",
        "organizations": "organization",
        "title": "concept",
        "keywords": "concept",
        "subject": "discipline",
        "document_language": "language",
        "contributor": "person"
    }

    for field in json_data:
        # Определяем тип сущности, если поле находится в списке основных полей
        entity_type = field_types.get(field) if field in CORE_METADATA_FIELDS else None
        
        if isinstance(enriched_data[field], list):
            enriched_field = []
            for item in enriched_data[field]:
                name = item if isinstance(item, str) else item.get("name", "")
                if not name:
                    continue
                wikidata_id = link_to_wikidata(name, entity_type)
                enriched_item = enrich_entity_with_wikidata(document, name, wikidata_id, field)
                enriched_field.append(enriched_item)
            enriched_data[field] = enriched_field
        elif isinstance(enriched_data[field], str):
            name = enriched_data[field]
            if name:
                wikidata_id = link_to_wikidata(name, entity_type)
                enriched_data[field] = enrich_entity_with_wikidata(document, name, wikidata_id, field)

    # Сохраняем метаданные в документ
    document.metadata = enriched_data
    document.save()

    return enriched_data