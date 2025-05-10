import time
import requests
from requests.exceptions import RequestException
from django.db import transaction
from django.utils import timezone
import logging

from apps.enhancer.models import WikidataEntity, Document, DocumentEntityRelation

# Глобальный кэш для результатов Wikidata (для работы в рамках одного запроса)
wikidata_cache = {}

CORE_METADATA_FIELDS = [
    "creator", "organizations", "title", "keywords", "dates", "summary", 
    "subject", "document_language", "identifier", "contributor", "rights"
]

def get_or_create_wikidata_entity(qid, name):
    """
    Проверяет, существует ли сущность Wikidata в базе данных, или создаёт новую.
    При необходимости обновляет метки и описания из Wikidata.
    Args:
        qid (str): Q-идентификатор Wikidata (например, "Q123")
        name (str): Название сущности (для меток)
    Returns:
        WikidataEntity: Объект сущности
    """
    try:
        # Пытаемся найти сущность в базе данных
        entity = WikidataEntity.objects.filter(qid=qid).first()
        
        if entity:
            # Сущность уже существует
            needs_update = False
            
            # Проверяем, нужно ли обновить метки
            if not entity.label_ru and not entity.label_en:
                needs_update = True
            
            # Проверяем, нужно ли обновить описания
            if not entity.description_ru and not entity.description_en:
                needs_update = True
            
            # Если нужно обновление или прошло более 30 дней с последнего обновления
            if needs_update or (entity.updated_at and (timezone.now() - entity.updated_at).days > 30):
                # Загружаем данные из Wikidata
                entity_data = fetch_wikidata_entity(qid)
                if entity_data:
                    # Обновляем метки
                    if entity_data.get('label_ru') and not entity.label_ru:
                        entity.label_ru = entity_data['label_ru']
                    if entity_data.get('label_en') and not entity.label_en:
                        entity.label_en = entity_data['label_en']
                    
                    # Обновляем описания
                    if entity_data.get('description_ru'):
                        entity.description_ru = entity_data['description_ru']
                    if entity_data.get('description_en'):
                        entity.description_en = entity_data['description_en']
                    
                    # Обновляем свойства
                    if entity_data.get('properties'):
                        entity.properties = entity_data['properties']
                    
                    # Сохраняем изменения
                    entity.save()
            
            return entity
        
        # Сущность не найдена, создаем новую
        # Сначала получаем данные из Wikidata
        entity_data = fetch_wikidata_entity(qid)
        
        if entity_data:
            # Создаем сущность с данными из Wikidata
            entity = WikidataEntity.objects.create(
                qid=qid,
                label_ru=entity_data.get('label_ru') or name,
                label_en=entity_data.get('label_en') or name,
                description_ru=entity_data.get('description_ru', ''),
                description_en=entity_data.get('description_en', ''),
                properties=entity_data.get('properties', {})
            )
        else:
            # Создаем сущность только с минимальными данными
            entity = WikidataEntity.objects.create(
            qid=qid,
                label_ru=name,
                label_en=name
        )
        
        return entity
        
    except Exception as e:
        print(f"Ошибка при получении или создании сущности Wikidata '{qid}': {e}")
        return None

def create_document_entity_relation(document, entity, field_category, name, confidence=1.0):
    """
    Создаёт связь между документом и сущностью Wikidata.
    Args:
        document (Document): Объект документа
        entity (WikidataEntity): Объект сущности Wikidata
        field_category (str): Категория поля
        name (str): Имя, использованное для упоминания сущности
        confidence (float): Уверенность связи (от 0 до 1)
    Returns:
        DocumentEntityRelation: Созданный объект связи
    """
    try:
        relation, created = DocumentEntityRelation.objects.get_or_create(
            document=document,
            entity=entity,
            field_category=field_category,
            name=name,
            defaults={'confidence': confidence}
        )
        return relation
    except Exception as e:
        print(f"Ошибка при создании связи между документом '{document.id}' и сущностью '{entity.qid}': {e}")
        return None

def enrich_entity_with_wikidata(document, name, qid, field_category):
    """
    Обогащает сущность данными Wikidata, создавая записи в базе данных.
    Args:
        document (Document): Объект документа
        name (str): Название сущности
        qid (str): Q-идентификатор Wikidata
        field_category (str): Категория поля
    Returns:
        dict: Словарь с полями name и wikidata или None
    """
    if not qid:
        return {"name": name, "wikidata": None}
    
    with transaction.atomic():
        entity = get_or_create_wikidata_entity(qid, name)
        if entity:
            create_document_entity_relation(document, entity, field_category, name)
            return {"name": name, "wikidata": qid}
        return {"name": name, "wikidata": None}

def update_document_wikidata_links(document):
    """
    Обновляет связи документа с сущностями Wikidata на основе его метаданных.
    Позволяет найти сущности Wikidata для полей, добавленных вручную.
    
    Args:
        document (Document): Объект документа
    
    Returns:
        int: Количество новых созданных связей
    """
    from apps.enhancer.processing.wikidata import link_to_wikidata, test_wikidata_connection, known_entities
    
    logger = logging.getLogger(__name__)
    
    # Счетчик новых связей
    new_links_count = 0
    # Флаг, показывающий, были ли использованы локальные кэши
    local_cache_used = False
    
    # Логируем данные документа для отладки
    logger.debug(f"Обновление связей для документа ID: {document.id}, название: {document.name}")
    logger.debug(f"Metadata: {document.metadata}")
    logger.debug(f"Meta_wikidata: {document.meta_wikidata}")
    
    # Создаю более подробное логирование для входных данных
    if document.metadata:
        for field, value in document.metadata.items():
            if isinstance(value, list):
                logger.debug(f"Поле {field} содержит список из {len(value)} элементов: {value}")
            else:
                logger.debug(f"Поле {field} содержит значение: {value}")
    
    # Проверяем наличие метаданных (теперь проверяем и metadata, и meta_wikidata)
    if not document.metadata and not document.meta_wikidata:
        logger.warning(f"Документ ID: {document.id} не имеет метаданных для обработки")
        return 0
    
    # Проверяем соединение с Wikidata
    wikidata_connection_ok = test_wikidata_connection()
    if not wikidata_connection_ok:
        logger.error("Нет соединения с Wikidata API. Используем только локальный кэш.")
    
    # Типы сущностей для каждого поля
    field_types = {
        "creator": "person",
        "author": "person", 
        "authors": "person",
        "organizations": "organization",
        "publisher": "organization",
        "title": "concept",
        "keywords": "concept",
        "subject": "concept",
        "document_language": "language",
        "language": "language",
        "contributor": "person",
        "contributors": "person",
        "array_key": "concept"  # Добавляем ключ array_key с типом concept
    }
    
    # Получаем текущие связи для проверки дубликатов
    existing_relations = {}
    for relation in document.entity_relations.all():
        if relation.field_category not in existing_relations:
            existing_relations[relation.field_category] = set()
        
        # Добавляем пару (поле_key, поле_value, QID) для проверки уникальности
        existing_relations[relation.field_category].add((relation.field_key, relation.field_value, relation.entity.qid))
    
    # Инициализируем meta_wikidata, если его нет
    meta_wikidata = document.meta_wikidata or {}
    
    # Проверяем метаданные в document.metadata
    if document.metadata:
    # Обрабатываем каждое поле метаданных
        for field in document.metadata:
            # Определяем тип сущности только для основных полей
            entity_type = field_types.get(field) if field in CORE_METADATA_FIELDS else None
            
            value = document.metadata[field]
            
            # Обрабатываем список значений
            if isinstance(value, list):
                # Для хранения связей Wikidata для этого поля
                if field not in meta_wikidata:
                    meta_wikidata[field] = {}
                
                logger.debug(f"Обработка поля-массива '{field}', тип: {entity_type}")
                
                for item in value:
                    # Если элемент - строка или словарь с полем name
                    name = None
                    if isinstance(item, str) and item.strip():
                        name = item
                    elif isinstance(item, dict) and 'name' in item and item['name'].strip():
                        name = item['name']
                    
                    if name:
                        logger.debug(f"Обработка элемента массива: '{name}' для поля '{field}'")
                        # Проверяем, есть ли уже связь в meta_wikidata
                        wikidata_id = None
                        if name in meta_wikidata[field]:
                            wikidata_id = meta_wikidata[field][name]
                        else:
                            # Нет связи, ищем в Wikidata
                            wikidata_id = link_to_wikidata(name, entity_type)
                            if wikidata_id:
                                meta_wikidata[field][name] = wikidata_id
                            elif name in known_entities:
                                # Если не нашли через API, но есть в локальном кэше
                                wikidata_id = known_entities[name]
                                meta_wikidata[field][name] = wikidata_id
                                local_cache_used = True
                                logger.info(f"Использую локальный кэш для '{name}': {wikidata_id}")
                        
                        if wikidata_id:
                            # Проверяем существующие связи
                            relation_key = (field, name, wikidata_id)
                            field_category = convert_field_to_category(field)
                            
                            if field_category not in existing_relations or relation_key not in existing_relations[field_category]:
                                # Создаем сущность и связь
                                entity = get_or_create_wikidata_entity(wikidata_id, name)
                                
                                if entity:
                                    relation, created = DocumentEntityRelation.objects.update_or_create(
                                        document=document,
                                        entity=entity,
                                        field_category=field_category,
                                        field_key=field,
                                        field_value=name,
                                        defaults={
                                            'name': name,
                                            'confidence': 1.0,
                                            'context': f'From metadata field: {field}'
                                        }
                                    )
                                    
                                    if created:
                                        logger.info(f"Создана новая связь: {name} -> {wikidata_id} для поля {field}")
                                        new_links_count += 1
            # Обрабатываем строковое значение
            elif isinstance(value, str) and value.strip():
                name = value
                
                # Проверяем, есть ли уже связь в meta_wikidata
                if field in meta_wikidata and isinstance(meta_wikidata[field], dict) and name in meta_wikidata[field]:
                    wikidata_id = meta_wikidata[field][name]
                    
                    # Проверяем существующие связи
                    field_category = convert_field_to_category(field)
                    relation_key = (field, name, wikidata_id)
                    
                    if field_category not in existing_relations or relation_key not in existing_relations[field_category]:
                        # Создаем сущность и связь
                        entity = get_or_create_wikidata_entity(wikidata_id, name)
                        
                        if entity:
                            relation, created = DocumentEntityRelation.objects.update_or_create(
                                document=document,
                                entity=entity,
                                field_category=field_category,
                                field_key=field,
                                field_value=name,
                                defaults={
                                    'name': name,
                                    'confidence': 1.0,
                                    'context': f'From metadata field: {field}'
                                }
                            )
                            
                            if created:
                                logger.info(f"Создана новая связь: {name} -> {wikidata_id} для поля {field}")
                                new_links_count += 1
                else:
                    # Нет связи, ищем в Wikidata
                    wikidata_id = link_to_wikidata(name, entity_type)
                    
                    if wikidata_id:
                        # Создаем сущность и связь
                        entity = get_or_create_wikidata_entity(wikidata_id, name)
                        field_category = convert_field_to_category(field)
                        
                        if entity:
                            relation, created = DocumentEntityRelation.objects.update_or_create(
                                document=document,
                                entity=entity,
                                field_category=field_category,
                                field_key=field,
                                field_value=name,
                                defaults={
                                    'name': name,
                                    'confidence': 1.0,
                                    'context': f'From metadata field: {field}'
                                }
                            )
                            
                            if created:
                                logger.info(f"Создана новая связь через API: {name} -> {wikidata_id} для поля {field}")
                                new_links_count += 1
                            
                            # Добавляем в meta_wikidata
                            if field not in meta_wikidata:
                                meta_wikidata[field] = {}
                            
                            meta_wikidata[field][name] = wikidata_id
    
    # Обрабатываем поля в meta_wikidata, если они не обработаны выше
    if document.meta_wikidata:
        for field_key, field_data in document.meta_wikidata.items():
            field_category = convert_field_to_category(field_key)
            entity_type = field_types.get(field_key, "concept")
            
            # Если поле - словарь (значение: qid)
            if isinstance(field_data, dict):
                for field_value, qid in field_data.items():
                    if not qid or not field_value:
                        continue
                    
                    # Проверяем существующие связи
                    relation_key = (field_key, field_value, qid)
                    
                    if field_category not in existing_relations or relation_key not in existing_relations[field_category]:
                        # Создаем сущность и связь
                        entity = get_or_create_wikidata_entity(qid, field_value)
                        
                        if entity:
                            relation, created = DocumentEntityRelation.objects.update_or_create(
                                document=document,
                                entity=entity,
                                field_category=field_category,
                                field_key=field_key,
                                field_value=field_value,
                                defaults={
                                    'name': field_value,
                                    'confidence': 1.0,
                                    'context': f'From meta_wikidata field: {field_key}'
                                }
                            )
                            
                            if created:
                                logger.info(f"Создана новая связь из meta_wikidata: {field_value} -> {qid} для поля {field_key}")
                                new_links_count += 1
                                
            # Если поле - список пар [значение, qid]
            elif isinstance(field_data, list):
                for item in field_data:
                    field_value = None
                    qid = None
                    
                    if isinstance(item, list) and len(item) >= 2:
                        field_value, qid = item
                    elif isinstance(item, dict) and 'value' in item and 'qid' in item:
                        field_value, qid = item['value'], item['qid']
                    
                    if not qid or not field_value:
                        continue
                    
                    # Проверяем существующие связи
                    relation_key = (field_key, field_value, qid)
                    
                    if field_category not in existing_relations or relation_key not in existing_relations[field_category]:
                        # Создаем сущность и связь
                        entity = get_or_create_wikidata_entity(qid, field_value)
                        
                        if entity:
                            relation, created = DocumentEntityRelation.objects.update_or_create(
                                document=document,
                                entity=entity,
                                field_category=field_category,
                                field_key=field_key,
                                field_value=field_value,
                                defaults={
                                    'name': field_value,
                                    'confidence': 1.0,
                                    'context': f'From meta_wikidata array: {field_key}'
                                }
                            )
                            
                            if created:
                                logger.info(f"Создана новая связь из meta_wikidata массива: {field_value} -> {qid} для поля {field_key}")
                                new_links_count += 1
    
    # Сохраняем обновленные метаданные и meta_wikidata
    if new_links_count > 0 or local_cache_used:
        document.meta_wikidata = meta_wikidata
        document.save()
        logger.debug(f"Сохранены обновленные meta_wikidata: {meta_wikidata}")
    else:
        logger.debug("Не было создано новых связей, meta_wikidata не обновлены")
    
    logger.info(f"Обновление завершено. Создано {new_links_count} новых связей.")
    return new_links_count

def convert_field_to_category(field_name):
    """
    Конвертирует название поля метаданных в категорию поля для DocumentEntityRelation
    """
    # Словарь соответствия названий полей и категорий
    field_to_category = {
        'creator': 'creator',
        'author': 'creator',
        'authors': 'creator',
        'keywords': 'keywords',
        'subject': 'subject',
        'language': 'document_language',
        'publisher': 'organizations',
        'contributor': 'contributor',
    }
    
    # Возвращаем соответствующую категорию или исходное название
    return field_to_category.get(field_name.lower(), field_name)

def search_and_link_entity_to_document(document, entity_name, category, entity_type=None, field_key=None, field_value=None):
    """
    Ищет сущность Wikidata по имени и связывает её с документом.
    
    Args:
        document (Document): Объект документа
        entity_name (str): Имя сущности для поиска
        category (str): Категория поля (keywords, creator, etc.)
        entity_type (str, optional): Тип сущности для поиска (person, organization, etc.)
        field_key (str, optional): Ключ поля метаданных
        field_value (str, optional): Значение поля метаданных
    
    Returns:
        DocumentEntityRelation or None: Созданная связь или None, если сущность не найдена
    """
    from apps.enhancer.processing.wikidata import link_to_wikidata, CORE_METADATA_FIELDS
    
    # Если тип сущности не указан, определяем по категории, но только для основных полей
    if not entity_type:
        entity_type_mapping = {
            "creator": "person",
            "organizations": "organization",
            "title": "concept",
            "keywords": "concept",
            "subject": "concept",
            "document_language": "language",
            "contributor": "person"
        }
        # Проверяем, является ли категория или поле основным
        actual_field = field_key if field_key else category
        if actual_field in CORE_METADATA_FIELDS:
            entity_type = entity_type_mapping.get(category, "concept")
        else:
            # Для не основных полей не используем тип
            entity_type = None
    
    # Ищем сущность в Wikidata
    wikidata_id = link_to_wikidata(entity_name, entity_type)
    
    if not wikidata_id:
        return None
    
    with transaction.atomic():
        # Получаем или создаем сущность
        entity = get_or_create_wikidata_entity(wikidata_id, entity_name)
        
        if not entity:
            return None
        
        # Используем field_key и field_value, если они переданы, 
        # иначе используем category и entity_name
        actual_field_key = field_key if field_key else category
        actual_field_value = field_value if field_value else entity_name
        
        # Создаем связь
        relation, created = DocumentEntityRelation.objects.update_or_create(
            document=document,
            entity=entity,
            field_category=category,
            field_key=actual_field_key,
            field_value=actual_field_value,
            defaults={
                'name': entity_name,  # Для обратной совместимости
                'confidence': 1.0,
                'context': f"Manually linked to {category}"
            }
        )
        
        # Обновляем meta_wikidata
        meta_wikidata = document.meta_wikidata or {}
        
        # Проверяем существование ключа и создаем структуру, если необходимо
        if actual_field_key not in meta_wikidata:
            if category in ['keywords', 'creator', 'subject', 'contributors']:
                # Для категорий, которые обычно массивы
                meta_wikidata[actual_field_key] = []
            else:
                # Для одиночных значений
                meta_wikidata[actual_field_key] = {}
        
        # Добавляем или обновляем значение
        if isinstance(meta_wikidata[actual_field_key], list):
            # Для массивов проверяем, что такого значения еще нет
            existing_items = [item for item in meta_wikidata[actual_field_key] 
                           if isinstance(item, list) and len(item) > 1 and item[0] == actual_field_value]
            
            if not existing_items:
                meta_wikidata[actual_field_key].append([actual_field_value, entity.qid])
        elif isinstance(meta_wikidata[actual_field_key], dict):
            # Для словарей добавляем пару значение: qid
            meta_wikidata[actual_field_key][actual_field_value] = entity.qid
        
        # Сохраняем обновленные метаданные
        document.meta_wikidata = meta_wikidata
        document.save(update_fields=['meta_wikidata'])
        
        return relation

def fetch_wikidata_entity(qid):
    """
    Получает данные о сущности Wikidata по QID
    Args:
        qid (str): Q-идентификатор Wikidata (например, "Q123")
    Returns:
        dict: Данные о сущности (метки, описания, свойства) или None
    """
    # Проверяем кэш
    cache_key = f"entity_data:{qid}"
    if cache_key in wikidata_cache:
        return wikidata_cache[cache_key]
    
    headers = {
        "User-Agent": "DocsMetadataEnhancerBot/1.0 (https://example.com; zheny@example.com)"
    }
    
    try:
        # Получаем основную информацию о сущности через Wikidata API
        api_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "languages": "ru|en",
            "format": "json"
        }
        
        response = requests.get(api_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if "entities" not in data or qid not in data["entities"]:
            return None
        
        entity_data = data["entities"][qid]
        
        # Извлекаем метки и описания
        result = {
            "label_ru": None,
            "label_en": None,
            "description_ru": None,
            "description_en": None,
            "properties": {}
        }
        
        # Получаем метки
        if "labels" in entity_data:
            if "ru" in entity_data["labels"]:
                result["label_ru"] = entity_data["labels"]["ru"]["value"]
            if "en" in entity_data["labels"]:
                result["label_en"] = entity_data["labels"]["en"]["value"]
        
        # Получаем описания
        if "descriptions" in entity_data:
            if "ru" in entity_data["descriptions"]:
                result["description_ru"] = entity_data["descriptions"]["ru"]["value"]
            if "en" in entity_data["descriptions"]:
                result["description_en"] = entity_data["descriptions"]["en"]["value"]
        
        # Получаем основные свойства через SPARQL (упрощенный вариант)
        try:
            important_properties = ["P31", "P279", "P570", "P19", "P569", "P106", "P131", "P17"]
            for prop in important_properties:
                if "claims" in entity_data and prop in entity_data["claims"]:
                    claims = entity_data["claims"][prop]
                    prop_values = []
                    
                    for claim in claims:
                        if "mainsnak" in claim and claim["mainsnak"]["snaktype"] == "value":
                            data_value = claim["mainsnak"]["datavalue"]
                            
                            if data_value["type"] == "wikibase-entityid":
                                value_qid = "Q" + str(data_value["value"]["numeric-id"])
                                
                                # Получаем метку для этой сущности
                                prop_entity = fetch_property_entity_label(prop, value_qid, headers)
                                if prop_entity:
                                    prop_values.append(prop_entity)
                            
                            elif data_value["type"] == "string":
                                prop_values.append({"value": data_value["value"]})
                            
                            elif data_value["type"] == "time":
                                time_value = data_value["value"]["time"]
                                prop_values.append({"value": time_value})
                    
                    # Если есть значения, добавляем свойство в результат
                    if prop_values:
                        # Получаем метку для самого свойства
                        prop_label = fetch_property_label(prop, headers)
                        result["properties"][prop] = {
                            "label": prop_label,
                            "values": prop_values
                        }
        except Exception as e:
            print(f"Ошибка при получении свойств для {qid}: {e}")
            # Продолжаем работу даже при ошибке получения свойств
        
        # Сохраняем в кэш
        wikidata_cache[cache_key] = result
        return result
    
    except RequestException as e:
        print(f"Ошибка сети при запросе к Wikidata для '{qid}': {e}")
        return None
    except Exception as e:
        print(f"Общая ошибка при получении данных о сущности '{qid}' из Wikidata: {e}")
        return None

def fetch_property_label(prop_id, headers):
    """
    Получает метку свойства Wikidata
    Args:
        prop_id (str): P-идентификатор свойства (например, "P31")
        headers (dict): HTTP-заголовки для запроса
    Returns:
        str: Метка свойства или prop_id, если метка не найдена
    """
    cache_key = f"prop_label:{prop_id}"
    if cache_key in wikidata_cache:
        return wikidata_cache[cache_key]
    
    try:
        api_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": prop_id,
            "languages": "ru|en",
            "format": "json"
        }
        
        response = requests.get(api_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if "entities" in data and prop_id in data["entities"] and "labels" in data["entities"][prop_id]:
            labels = data["entities"][prop_id]["labels"]
            if "ru" in labels:
                label = labels["ru"]["value"]
            elif "en" in labels:
                label = labels["en"]["value"]
            else:
                label = prop_id
            
            wikidata_cache[cache_key] = label
            return label
        
        return prop_id
    
    except Exception:
        return prop_id

def fetch_property_entity_label(prop_id, value_qid, headers):
    """
    Получает метку сущности, которая является значением свойства
    Args:
        prop_id (str): P-идентификатор свойства (например, "P31")
        value_qid (str): Q-идентификатор значения свойства (например, "Q5")
        headers (dict): HTTP-заголовки для запроса
    Returns:
        dict: Словарь с полями value (метка) и qid (Q-идентификатор) или None
    """
    cache_key = f"entity_label:{value_qid}"
    if cache_key in wikidata_cache:
        return wikidata_cache[cache_key]
    
    try:
        api_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbgetentities",
            "ids": value_qid,
            "languages": "ru|en",
            "format": "json"
        }
        
        response = requests.get(api_url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if "entities" in data and value_qid in data["entities"] and "labels" in data["entities"][value_qid]:
            labels = data["entities"][value_qid]["labels"]
            result = {"qid": value_qid}
            
            if "ru" in labels:
                result["value"] = labels["ru"]["value"]
            elif "en" in labels:
                result["value"] = labels["en"]["value"]
            else:
                result["value"] = value_qid
            
            wikidata_cache[cache_key] = result
            return result
        
        return {"qid": value_qid, "value": value_qid}
    
    except Exception:
        return {"qid": value_qid, "value": value_qid} 