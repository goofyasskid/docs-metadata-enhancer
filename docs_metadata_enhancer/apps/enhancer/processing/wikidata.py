import time
import requests
from requests.exceptions import RequestException



# Глобальный кэш для результатов Wikidata
wikidata_cache = {}

def link_to_wikidata(entity_name, entity_type=None):
    """
    Связывает сущность с Wikidata, возвращая id, label_en, label_ru.
    Args:
        entity_name (str): Название сущности (например, "Университет Джорджии")
        entity_type (str): Тип сущности (person, organization, concept, language, discipline)
    Returns:
        dict: {'id': 'Q123', 'label_en': 'Name', 'label_ru': 'Имя'} или None
    """
    # Проверяем кэш
    cache_key = f"{entity_name}:{entity_type}"
    if cache_key in wikidata_cache:
        return wikidata_cache[cache_key]

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
        response = requests.get(search_url, params=params, headers=headers)
        response.raise_for_status()
        search_results = response.json().get("search", [])

        # Если ничего не найдено, пробуем на английском
        if not search_results:
            params["language"] = "en"
            params["uselang"] = "en"
            response = requests.get(search_url, params=params, headers=headers)
            response.raise_for_status()
            search_results = response.json().get("search", [])

        if not search_results:
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
        if entity_type and entity_type in valid_types:
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
                time.sleep(0.5)  # Задержка для соблюдения лимитов
                sparql_response = requests.get(sparql_url, params=sparql_params, headers=headers)
                sparql_response.raise_for_status()
                types = [binding["type"]["value"].split("/")[-1] for binding in sparql_response.json().get("results", {}).get("bindings", [])]
                if any(t in valid_types[entity_type] for t in types):
                    best_result = result
                    break
        else:
            # Берем первый результат, если тип не указан или не требуется фильтрация
            best_result = search_results[0]

        if not best_result:
            # Дополнительная попытка: ищем без строгой фильтрации, но с приоритетом по совпадению метки
            for result in search_results:
                label = result.get("label", "").lower()
                if label == entity_name.lower():
                    best_result = result
                    break
            if not best_result:
                best_result = search_results[0]  # Берем первый, если нет точного совпадения

        entity_id = best_result["id"]

        # Шаг 2: Извлечение метаданных через wbgetentities
        entity_url = "https://www.wikidata.org/w/api.php"
        entity_params = {
            "action": "wbgetentities",
            "ids": entity_id,
            "languages": "en|ru",
            "props": "labels",
            "format": "json"
        }
        time.sleep(0.5)  # Задержка
        entity_response = requests.get(entity_url, params=entity_params, headers=headers)
        entity_response.raise_for_status()
        entity_data = entity_response.json().get("entities", {}).get(entity_id, {})

        # Извлекаем метки
        labels = entity_data.get("labels", {})
        label_en = labels.get("en", {}).get("value", entity_name)
        label_ru = labels.get("ru", {}).get("value", entity_name)

        result = {
            "id": entity_id,
            "label_en": label_en,
            "label_ru": label_ru
        }
        wikidata_cache[cache_key] = result
        return result

    except RequestException as e:
        print(f"Ошибка при запросе к Wikidata для '{entity_name}': {e}")
        wikidata_cache[cache_key] = None
        return None
    except Exception as e:
        print(f"Общая ошибка при связывании '{entity_name}' с Wikidata: {e}")
        wikidata_cache[cache_key] = None
        return None
    
    
def enrich_with_wikidata(json_data):
    """
    Обогащает JSON данными из Wikidata для всех полей, кроме summary и dates.
    Args:
        json_data (dict): Входной JSON
    Returns:
        dict: JSON с добавленным полем wikidata
    """
    enriched_data = json_data.copy()
    
    # Типы сущностей для каждого поля
    field_types = {
        "author": "person",
        "organizations": "organization",
        "topic": "concept",
        "keywords": "concept",
        "language": "language",
        "subject_area": "discipline",
        "document_language": "language"
    }

    for field, entity_type in field_types.items():
        if field in enriched_data and isinstance(enriched_data[field], list):
            enriched_field = []
            for item in enriched_data[field]:
                name = item if isinstance(item, str) else item.get("name", "")
                if not name:
                    continue
                print(f"Linking '{name}' as {entity_type}...")
                wikidata_data = link_to_wikidata(name, entity_type)
                enriched_item = {
                    "name": name,
                    "wikidata": wikidata_data
                }
                print(f"Result for '{name}': {wikidata_data}")
                enriched_field.append(enriched_item)
            enriched_data[field] = enriched_field

    return enriched_data