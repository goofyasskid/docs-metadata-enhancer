import json
import os
import time
from pathlib import Path

from apps.enhancer.loaders.pdf_loader import load_pdf
from apps.enhancer.openai.chat_gpt import (finalize_entities,
                                           process_text_with_chatgpt)
from apps.enhancer.processing.post_processing import merge_entities
from apps.enhancer.processing.pre_processing import (clean_text,
                                                     remove_stopwords,
                                                     split_text)
from apps.enhancer.processing.wikidata import enrich_with_wikidata
from django.contrib import messages
from django.shortcuts import render


def index(request):
    result = None
    pdf_path = None
    json_path = None

    if request.method == 'POST':
        pdf_file = request.FILES.get('pdf_file')
        if not pdf_file:
            messages.error(request, "Пожалуйста, выберите PDF-файл.")
        elif not pdf_file.name.endswith('.pdf'):
            messages.error(request, "Файл должен быть в формате PDF.")
        else:
            try:
                # Генерируем уникальное имя файла с временной меткой
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                pdf_filename = f"{timestamp}_{pdf_file.name}"
                pdf_path = Path('media/docs') / pdf_filename
                json_filename = f"{timestamp}_{pdf_file.name.rsplit('.', 1)[0]}.json"
                json_path = Path('media/json') / json_filename

                # Создаём директории, если их нет
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                json_path.parent.mkdir(parents=True, exist_ok=True)

                # Сохраняем PDF
                with open(pdf_path, 'wb') as f:
                    for chunk in pdf_file.chunks():
                        f.write(chunk)
                
                # Обработка PDF
                pages = load_pdf(str(pdf_path))
                if pages:
                    full_text = " ".join([page.page_content for page in pages])
                    cleaned_text = clean_text(full_text)
                    final_text = remove_stopwords(cleaned_text)
                    chunks = split_text(final_text, chunk_size=2000, chunk_overlap=200)
                    
                    entities_list = []
                    for i, chunk in enumerate(chunks):
                        entities = process_text_with_chatgpt(chunk)
                        if entities:
                            entities_list.append(entities)
                        else:
                            messages.warning(request, f"Не удалось обработать чанк {i+1}.")
                    
                    # Объединяем и финализируем сущности
                    merged_entities = merge_entities(entities_list)
                    final_entities = finalize_entities(merged_entities)
                    
                    # Обогащаем с Wikidata
                    enriched_entities = enrich_with_wikidata(final_entities)
                    
                    # Форматируем результат как JSON
                    result = json.dumps(enriched_entities, indent=2, ensure_ascii=False)
                    
                    # Сохраняем JSON
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(enriched_entities, f, indent=2, ensure_ascii=False)
                    
                    messages.success(request, f"PDF успешно обработан! Файлы сохранены: {pdf_filename}, {json_filename}")
                else:
                    messages.error(request, "Не удалось загрузить PDF.")
                    if pdf_path.exists():
                        pdf_path.unlink()
                
            except Exception as e:
                messages.error(request, f"Ошибка обработки PDF: {str(e)}")
                if pdf_path and pdf_path.exists():
                    pdf_path.unlink()
    
    return render(request, 'enhancer/index.html', {'result': result, 'pdf_path': pdf_path, 'json_path': json_path})