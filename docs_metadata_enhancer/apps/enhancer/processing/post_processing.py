import json
from collections import defaultdict

def validate_json(response):
    """
    Проверяет, является ли ответ валидным JSON.
    Args:
        response (str): Ответ от ChatGPT
    Returns:
        dict: Распарсенный JSON или None, если невалиден
    """
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"Невалидный JSON: {e}")
        return None

# def merge_entities(entities_list):
#     """
#     Объединяет сущности из списка и удаляет дубликаты.
#     Args:
#         entities_list (list): Список словарей с сущностями
#     Returns:
#         dict: Объединенные сущности без дубликатов
#     """
#     merged = {
#         "author": set(),
#         "organizations": set(),
#         "topic": "",
#         "keywords": set(),
#         "dates": set(),
#         "language": "",
#         "summary": set(),
#         "subject_area": set(),
#         "document_language": ""
#     }
    
#     for entities in entities_list:
#         if not entities:
#             continue
#         # Объединяем списки (авторы, организации, ключевые слова, даты, предметные области)
#         merged["author"].update(entities.get("author", []))
#         merged["organizations"].update(entities.get("organizations", []))
#         merged["keywords"].update(entities.get("keywords", []))
#         merged["dates"].update(entities.get("dates", []))
#         merged["subject_area"].update(entities.get("subject_area", []))
#         # Для полей с одним значением берём первое непустое
#         if not merged["topic"] and entities.get("topic"):
#             merged["topic"] = entities["topic"]
#         if not merged["language"] and entities.get("language"):
#             merged["language"] = entities["language"]
#         if not merged["document_language"] and entities.get("document_language"):
#             merged["document_language"] = entities["document_language"]
#         # Объединяем summary как набор предложений
#         if entities.get("summary"):
#             sentences = entities["summary"].strip().split(". ")
#             merged["summary"].update([s.strip() for s in sentences if s.strip()])
    
#     # Преобразуем set в list и формируем итоговый summary
#     result = {
#         key: list(values) if key in {"author", "organizations", "keywords", "dates", "subject_area"} else values
#         for key, values in merged.items()
#     }
#     result["summary"] = " ".join(merged["summary"]) if merged["summary"] else ""
    
#     return result

def merge_entities(entities_list):
    """
    Объединяет сущности из списка без удаления дубликатов.
    Args:
        entities_list (list): Список словарей с сущностями
    Returns:
        dict: Объединённые сущности
    """
    merged = {
        "author": [],
        "organizations": [],
        "topic": [],
        "keywords": [],
        "dates": [],
        "language": [],
        "summary": [],
        "subject_area": [],
        "document_language": []
    }
    
    for entities in entities_list:
        if not entities:
            continue
        merged["author"].extend(entities.get("author", []))
        merged["organizations"].extend(entities.get("organizations", []))
        merged["keywords"].extend(entities.get("keywords", []))
        merged["dates"].extend(entities.get("dates", []))
        merged["subject_area"].extend(entities.get("subject_area", []))
        if entities.get("topic"):
            merged["topic"].append(entities["topic"])
        if entities.get("language"):
            merged["language"].append(entities["language"])
        if entities.get("document_language"):
            merged["document_language"].append(entities["document_language"])
        if entities.get("summary"):
            merged["summary"].append(entities["summary"])
    
    return merged