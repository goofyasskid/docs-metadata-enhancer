import json
from docs_metadata_enhancer.settings import GIGACHAT_CREDENTIALS
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from apps.enhancer.processing.utils import validate_json
from apps.enhancer.LLM.prompts.ner_prompt import ner_prompt_3,ner_prompt_3

# Инициализация GigaChat
giga = GigaChat(credentials=GIGACHAT_CREDENTIALS, verify_ssl_certs=False, model="GigaChat-2-Max")

def process_text_with_gigachat(text):
    """
    Обрабатывает текст с помощью GigaChat для извлечения сущностей.
    Args:
        text (str): Текст для обработки
    Returns:
        dict: Извлеченные сущности в формате JSON или None
    """
    try:
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=ner_prompt_3),
                Messages(role=MessagesRole.USER, content=text)
            ],
            temperature=0.3,
            max_tokens=1000
        )
        response = giga.chat(payload)
        result = response.choices[0].message.content
        parsed_result = validate_json(result)
        
        if parsed_result is None:
            print("Попытка исправить невалидный JSON...")
            parsed_result = fix_json_response(ner_prompt_3, result)
        
        return parsed_result
    except Exception as e:
        print(f"Ошибка обработки текста с GigaChat: {e}")
        return None

def fix_json_response(system_prompt, invalid_response):
    """
    Запрашивает исправление невалидного JSON у GigaChat.
    Args:
        system_prompt (str): Системный промпт для задачи
        invalid_response (str): Невалидный ответ
    Returns:
        dict: Исправленный JSON или None
    """
    fix_prompt = (
        f"Ответ не является валидным JSON. Перепишите его в правильном формате JSON. "
        f"Исходный ответ: {invalid_response}"
    )
    try:
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                Messages(role=MessagesRole.USER, content=fix_prompt)
            ],
            temperature=0.3,
            max_tokens=1000
        )
        response = giga.chat(payload)
        fixed_result = response.choices[0].message.content
        return validate_json(fixed_result)
    except Exception as e:
        print(f"Ошибка при исправлении JSON: {e}")
        return None

def finalize_entities(merged_entities):
    """
    Отправляет объединённые сущности в GigaChat для финальной обработки, удаления дубликатов и выделения основной информации.
    Args:
        merged_entities (dict): Объединённые сущности из всех чанков
    Returns:
        dict: Финальный JSON с обработанными сущностями или None
    """
    final_prompt = """
    Вы — эксперт по обработке и агрегации данных. Ваша задача — обработать JSON с сущностями, извлечёнными из текста (вероятно, из нескольких фрагментов и предыдущим этапом обработки), удалить дубликаты, выбрать наиболее релевантную информацию и оставить только основные данные. Верните результат в формате JSON, строго соответствующем следующей структуре, без дополнительного текста:
    {
    "creator": ["Имя создателя 1", ...],
    "organizations": ["Название организации 1", ...],
    "publisher": "Название публикующей организации",
    "title": "Название текста",
    "keywords": ["ключевое слово 1", "ключевое слово 2", ...],
    "summary": "краткое описание",
    "subject": ["предметная область 1", ...],
    "document_language": "язык документа",
    "identifier": "идентификатор ресурса (DOI, URL и т.д.)",
    "contributor": ["контрибьютор 1", ...],
    "rights": "информация о правах или лицензии",
    "persons": ["Упомянутая персона 1", ...]
    }

    Правила:
    - Для списков (creator, organizations, keywords, subject, contributor, persons) удалите дубликаты. Списки должны содержать уникальные значения.
    - Для поля keywords оставьте не более пяти-семи наиболее значимых ключевых слов, отражающих главную суть текста.
    - Для поля title выберите или сгенерируйте одно наиболее полное и точное название, отражающее суть всего текста. Если входной JSON содержит несколько вариантов title из разных фрагментов, объедините их или выберите лучший.
    - Для поля summary составьте одно краткое, но исчерпывающее описание (2-3 предложения), объединяющее основные аспекты текста без повторов. Если входной JSON содержит несколько summary, синтезируйте из них одно обобщающее.
    - Для поля publisher выберите одно наиболее релевантное название организации-издателя.
    - Для поля document_language выберите один язык, наиболее подходящий для всего текста.
    - Для поля identifier выберите один наиболее релевантный и полный идентификатор (например, DOI предпочтительнее общего URL страницы, если оба присутствуют).
    - Для поля rights выберите одну наиболее подходящую и полную информацию о правах или лицензии.
    - Если для какого-то поля информация отсутствует во входном JSON или не может быть однозначно определена, оставьте его пустым (`[]` для списков, `null` или `""` для строк).

    Входной JSON:
    """
    try:
        input_json = json.dumps(merged_entities, ensure_ascii=False)
        payload = Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=final_prompt),
                Messages(role=MessagesRole.USER, content=input_json),
                Messages(role=MessagesRole.USER, content="Обработайте входной JSON и верните результат.")
            ],
            temperature=0.3,
            max_tokens=1000
        )
        response = giga.chat(payload)
        result = response.choices[0].message.content
        parsed_result = validate_json(result)
        
        if parsed_result is None:
            print("Попытка исправить невалидный JSON в финальной обработке...")
            parsed_result = fix_json_response(final_prompt, result)
        
        return parsed_result
    except Exception as e:
        print(f"Ошибка финальной обработки сущностей: {e}")
        return None