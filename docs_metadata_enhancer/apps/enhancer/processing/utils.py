import json


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