
import json


from docs_metadata_enhancer.settings import OPENAI_API_KEY

import openai
from apps.enhancer.processing.utils import validate_json
from apps.enhancer.LLM.prompts.ner_prompt import ner_prompt_2
from apps.enhancer.LLM.prompts.ner_prompt import ner_prompt

openai.api_key = OPENAI_API_KEY

def process_text_with_chatgpt(text):
    """
    Обрабатывает текст с помощью ChatGPT для извлечения сущностей.
    Args:
        text (str): Текст для обработки
    Returns:
        dict: Извлеченные сущности в формате JSON или None
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ner_prompt_2},
                {"role": "user", "content": text},
                {"role": "assistant", "content": ""}
            ],
            temperature=0.3
        )
        
        result = response['choices'][0]['message']['content']
        parsed_result = validate_json(result)
        
        # Если JSON невалиден, пробуем исправить
        if parsed_result is None:
            print("Попытка исправить невалидный JSON...")
            parsed_result = fix_json_response(text, result)
        
        return parsed_result
    
    except Exception as e:
        print(f"Ошибка обработки текста с ChatGPT: {e}")
        return None
    
    
def fix_json_response(original_text, invalid_response):
    """
    Запрашивает исправление невалидного JSON у ChatGPT.
    Args:
        original_text (str): Исходный текст
        invalid_response (str): Невалидный ответ
    Returns:
        dict: Исправленный JSON или None
    """
    fix_prompt = (
        f"Ответ не является валидным JSON. Перепишите его в правильном формате JSON. "
        f"Исходный ответ: {invalid_response}"
    )
    try:
        fix_response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": ner_prompt},
                {"role": "user", "content": original_text},
                {"role": "assistant", "content": invalid_response},
                {"role": "user", "content": fix_prompt}
            ],
            temperature=0.3
        )
        fixed_result = fix_response['choices'][0]['message']['content']
        return validate_json(fixed_result)  # Повторная проверка
    except Exception as e:
        print(f"Ошибка при исправлении JSON: {e}")
        return None
    
    
def finalize_entities(merged_entities):
    """
    Отправляет объединённые сущности в ChatGPT для финальной обработки, удаления дубликатов и выделения основной информации.
    Args:
        merged_entities (dict): Объединённые сущности из всех чанков
    Returns:
        dict: Финальный JSON с обработанными сущностями или None
    """
    final_prompt = """
    Вы — эксперт по обработке данных. Ваша задача — обработать JSON с сущностями, извлечёнными из текста, удалить дубликаты и оставить только основную информацию. Верните результат в формате JSON, строго соответствующем следующей структуре, без дополнительного текста:
    {
      "author": ["Имя автора"],
      "organizations": ["Название организации", ...],
      "topic": "Главная тема текста",
      "keywords": ["ключевое слово 1", "ключевое слово 2", ...],
      "dates": ["дата 1", "дата 2", ...],
      "summary": "краткое описание текста",
      "subject_area": ["предметная область 1", ...],
      "document_language": "язык документа"
    }

    Правила:
    - Удалите дубликаты из списков (author, organizations, keywords, dates, subject_area).
    - Для поля keywords оставь четыре-пять ключевых слов отражающих главную суть.
    - Для поля topic выберите одну главную тему, наиболее точно отражающую суть текста.
    - Для полей language и document_language выберите один язык, наиболее подходящий для текста.
    - Для summary составьте краткое описание, объединяющее основные аспекты текста без повторов.
    - Если данных недостаточно, оставьте поля пустыми.

    Входной JSON:
    """
    try:
        # Преобразуем merged_entities в строку JSON для отправки
        input_json = json.dumps(merged_entities, ensure_ascii=False)
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": final_prompt},
                {"role": "user", "content": input_json},
                {"role": "user", "content": "Обработайте входной JSON и верните результат."}
            ],
            temperature=0.3
        )
        
        result = response['choices'][0]['message']['content']
        parsed_result = validate_json(result)
        
        if parsed_result is None:
            print("Попытка исправить невалидный JSON в финальной обработке...")
            parsed_result = fix_json_response("", result)
        
        return parsed_result
    
    except Exception as e:
        print(f"Ошибка финальной обработки сущностей: {e}")
        return None