import json

import os

from apps.enhancer.loaders.pdf_loader import load_pdf
from apps.enhancer.openai.chat_gpt import finalize_entities, process_text_with_chatgpt
from apps.enhancer.processing.post_processing import merge_entities
from apps.enhancer.processing.pre_processing import clean_text, remove_stopwords, split_text
from apps.enhancer.processing.wikidata import enrich_with_wikidata


# Пример использования
file_path = "C://Users/zheny/Downloads/ВКР.pdf"

        
# if __name__ == "__main__":
#     # Путь к PDF
#     current_dir = os.path.dirname(os.path.abspath(__file__))
#     pdf_path = "C://Users/zheny/Downloads/test2.pdf"
    
#     # Загрузка PDF
#     pages = load_pdf(pdf_path)
#     if pages:
#         print(f"Успешно загружены {len(pages)} страниц")
        
#         # Объединяем текст всех страниц и очищаем
#         full_text = " ".join([page.page_content for page in pages])
        
#         cleaned_text = clean_text(full_text)
#         print(f"\nОчищенный текст:\n{cleaned_text[:500]}...")
#         print(f'Длина текста: {len(cleaned_text)}')
        
#         final_text = remove_stopwords(cleaned_text)
#         print(f"\nУбраны стопслова:\n{final_text[:500]}...")
#         print(f'Длина текста: {len(final_text)}')
#         # Разбиваем текст на чанки
#         chunks = split_text(final_text, chunk_size=1000, chunk_overlap=200)
#         print(f"Текст разбит на {len(chunks)} чанков")
        
#         # Обрабатываем каждый чанк с ChatGPT
#         entities_list = []
#         for i, chunk in enumerate(chunks):
#             print(f"Processing chunk {i+1}/{len(chunks)}...")
#             entities = process_text_with_chatgpt(chunk)
#             if entities:
#                 entities_list.append(entities)
#             else:
#                 print(f"Failed to process chunk {i+1}")
        
#         # Объединяем сущности
#         merged_entities = merge_entities(entities_list)
#         print("\nMerged entities (before final processing):")
#         print(json.dumps(merged_entities, indent=2, ensure_ascii=False))
        
        
#         # Финальная обработка сущностей
#         final_entities = finalize_entities(merged_entities)
        
#         # Выводим результат
#         print("\nFinal extracted entities:")
#         print(json.dumps(final_entities, indent=2, ensure_ascii=False))
        
        
        
if __name__ == "__main__":
    # Путь к PDF
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # pdf_path = "C://Users/zheny/Downloads/test.pdf"
    
    # Синтетический JSON для тестирования
    synthetic_json = {
        "author": ["Э. П. Торренс", "И. А. Иванова"],
        "organizations": ["Университет Джорджии", "Московский государственный университет"],
        "topic": ["Поддержка талантливой молодежи", "Психологическая диагностика одарённости", "Академическая и творческая одаренность"],
        "keywords": ["талантливая молодежь", "психологическая диагностика", "одарённость", "интеллект", "творчество", "лидерство", "социальные таланты", "инициативность", "психомоторные способности"],
        "dates": ["1966", "2023"],
        "language": ["русский", "английский"],
        "summary": [
            "Текст обсуждает методы и формы поддержки талантливой молодежи в образовательных учреждениях.",
            "Рассматривается психологическая диагностика одарённости и её роль в выявлении академической и творческой одарённости.",
            "Обсуждаются способности лидерских и творческих людей, их влияние на окружающих и важность инициативности."
        ],
        "subject_area": ["Образование", "Социология", "Психология", "Искусство", "Спорт"],
        "document_language": ["русский"]
    }
    
    # Используем синтетический JSON для теста
    final_entities = synthetic_json
    
    # Финальная обработка сущностей
    print("\nFinal extracted entities (before Wikidata):")
    print(json.dumps(final_entities, indent=2, ensure_ascii=False))
    
    # Обогащение с Wikidata
    enriched_entities = enrich_with_wikidata(final_entities)
    
    # Вывод результата
    print("\nEnriched entities with Wikidata:")
    print(json.dumps(enriched_entities, indent=2, ensure_ascii=False))