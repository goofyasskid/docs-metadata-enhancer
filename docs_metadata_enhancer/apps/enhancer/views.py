import json
import logging
import os
import time
from pathlib import Path

from apps.enhancer.loaders.pdf_loader import load_pdf
from apps.enhancer.LLM.openai.chat_gpt import (finalize_entities,
                                           process_text_with_chatgpt)
from apps.enhancer.processing.post_processing import merge_entities
from apps.enhancer.processing.pre_processing import (clean_text,
                                                     remove_stopwords,
                                                     split_text)
from apps.enhancer.processing.wikidata import enrich_with_wikidata
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse, FileResponse
from .models import DocumentEntityRelation, Folder, Document, WikidataEntity
from .tasks import process_document
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.template.loader import render_to_string
from celery.result import AsyncResult
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from django.db.models import Q, Count
from django.utils.text import slugify

# Настройка логирования
logger = logging.getLogger(__name__)


@login_required
def file_system(request, folder_id=None):
    if folder_id:
        current_folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
        folders = current_folder.children.all()
    else:
        current_folder = None
        # Получаем корневые папки текущего пользователя
        folders = Folder.objects.filter(
            owner=request.user,
            parent__isnull=True
        ).order_by('name')
    
    # Получаем документы для текущей папки
    documents = Document.objects.filter(
        owner=request.user,
        folder=current_folder
    ).order_by('name')
    
    return render(request, 'enhancer/index.html', {
        'folders': folders,
        'documents': documents,
        'current_folder': current_folder
    })
    
    
@login_required
def create_folder(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        parent_id = request.POST.get('parent_id')
        
        if not name:
            messages.error(request, "Название папки не может быть пустым")
            return redirect('enhancer:file_system')
        
        try:
            parent = None
            if parent_id:
                parent = get_object_or_404(Folder, id=parent_id, owner=request.user)
            
            Folder.objects.create(
                name=name,
                parent=parent,
                owner=request.user
            )
            messages.success(request, f"Папка '{name}' успешно создана")
            
            # Перенаправляем на текущую папку, если она есть
            if parent_id:
                return redirect('enhancer:folder_detail', folder_id=parent_id)
            return redirect('enhancer:file_system')
            
        except Exception as e:
            messages.error(request, f"Ошибка при создании папки: {str(e)}")
            if parent_id:
                return redirect('enhancer:folder_detail', folder_id=parent_id)
            return redirect('enhancer:file_system')
    
    return redirect('enhancer:file_system')


def delete_folder(request):
    if request.method == 'POST':
        folder_id = request.POST.get('folder_id')
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
            folder_name = folder.name
            folder.delete()
            messages.success(request, f"Папка '{folder_name}' успешно удалена")
        except Exception as e:
            messages.error(request, f"Ошибка при удалении папки: {str(e)}")
    
    return redirect('enhancer:file_system')

def upload_file(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        file = request.FILES.get('file')
        folder_id = request.POST.get('folder_id')
        
        if not file:
            messages.error(request, "Необходимо выбрать файл")
            return redirect('enhancer:file_system')
        
        try:
            # Если имя не указано, берем имя из загруженного файла
            if not name:
                name = file.name
            
            # Убираем расширение из имени, если оно есть
            name = name.rsplit('.', 1)[0]
            
            folder = None
            if folder_id:
                folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
            
            logger.info(f"Начинаем загрузку файла '{name}' пользователем {request.user.username}")
            
            # Создаем документ
            document = Document.objects.create(
                name=name,
                file=file,
                folder=folder,
                owner=request.user
            )
            
            # Проверяем, работает ли Celery в eager режиме (синхронно)
            from celery import current_app
            is_eager = getattr(current_app.conf, 'task_always_eager', False)
            
            if is_eager:
                # В синхронном режиме (Redis недоступен)
                logger.info(f"Celery работает в eager режиме. Запускаем синхронную обработку документа '{name}' (ID: {document.id})")
                messages.info(request, "Обработка будет выполнена синхронно, это может занять некоторое время...")
                
                # Вызываем задачу напрямую (синхронно)
                result = process_document(document.id)
                
                if result:
                    messages.success(request, f"Файл '{name}' успешно загружен и обработан")
                else:
                    messages.warning(request, f"Файл '{name}' загружен, но при обработке возникли проблемы. Проверьте лог ошибок.")
            else:
                # Стандартный асинхронный режим
                # Запускаем фоновую задачу и получаем ее ID
                task = process_document.delay(document.id)
                task_id = task.id
                
                # Обновляем документ с ID задачи Celery
                document.task_id = task_id
                document.save(update_fields=['task_id'])
                
                logger.info(f"Документ '{name}' (ID: {document.id}) отправлен на обработку. Task ID: {task_id}")
                messages.success(request, f"Файл '{name}' успешно загружен и отправлен на обработку")
            
            # Перенаправляем на текущую папку или на главную страницу
            if folder_id:
                return redirect('enhancer:folder_detail', folder_id=folder_id)
            return redirect('enhancer:file_system')
            
        except Exception as e:
            logger.error(f"Ошибка при загрузке файла: {str(e)}", exc_info=True)
            messages.error(request, f"Ошибка при загрузке файла: {str(e)}")
            if folder_id:
                return redirect('enhancer:folder_detail', folder_id=folder_id)
            return redirect('enhancer:file_system')
    
    return redirect('enhancer:file_system')

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

def rename_folder(request):
    if request.method == 'POST':
        folder_id = request.POST.get('folder_id')
        new_name = request.POST.get('name')
        
        if not new_name:
            messages.error(request, "Название папки не может быть пустым")
            return redirect('enhancer:file_system')
        
        try:
            folder = get_object_or_404(Folder, id=folder_id, owner=request.user)
            old_name = folder.name
            folder.name = new_name
            folder.save()
            messages.success(request, f"Папка '{old_name}' переименована в '{new_name}'")
            
            # Перенаправляем на текущую папку, если она есть
            if folder.parent:
                return redirect('enhancer:folder_detail', folder_id=folder.parent.id)
            return redirect('enhancer:file_system')
            
        except Exception as e:
            messages.error(request, f"Ошибка при переименовании папки: {str(e)}")
            if folder.parent:
                return redirect('enhancer:folder_detail', folder_id=folder.parent.id)
            return redirect('enhancer:file_system')
    
    return redirect('enhancer:file_system')

@ensure_csrf_cookie
def document_detail(request, document_id):
    document = get_object_or_404(Document, id=document_id, owner=request.user)
    
    if request.method == 'POST':
        try:
            metadata_from_form = json.loads(request.POST.get('processed_metadata', '{}'))
            
            # Очищаем метаданные от пустых массивов или массивов с пустыми объектами/строками,
            # чтобы избежать сохранения {'array_key': [{}]} или {'array_key': ['']}
            cleaned_metadata = {}
            for key, value in metadata_from_form.items():
                if isinstance(value, list):
                    # Фильтруем пустые строки и None из списков простых значений
                    processed_list = [item for item in value if item is not None and str(item).strip() != ""]
                    if processed_list: # Сохраняем ключ, только если список не пуст после фильтрации
                        cleaned_metadata[key] = processed_list
                elif isinstance(value, dict):
                    # Можно добавить логику для очистки словарей, если необходимо
                    cleaned_metadata[key] = value 
                elif value is not None and str(value).strip() != "":
                     cleaned_metadata[key] = value

            document.metadata = cleaned_metadata
            # meta_wikidata обновляется отдельно через свои механизмы, здесь не трогаем напрямую
            document.save()
            
            update_entity_relations_from_meta_wikidata(document) # Эта функция должна быть проверена на совместимость
            
            messages.success(request, "Метаданные успешно сохранены")
            return redirect('enhancer:document_detail', document_id=document.id)
        except Exception as e:
            messages.error(request, f"Ошибка при сохранении: {str(e)}")
            return redirect('enhancer:document_detail', document_id=document.id)

    file_size = 0
    if document.file:
        file_size = round(document.file.size / (1024 * 1024), 2)
    
    raw_metadata = document.metadata or {}
    
    # Отладочный вывод - посмотрим, что находится в raw_metadata
    logger.debug(f"RAW METADATA: {raw_metadata}")
    
    # Готовим данные для отображения в форме. Все значения должны быть строками или списками строк.
    display_values_for_form = {}
    for key, db_value in raw_metadata.items():
        if isinstance(db_value, list):
            processed_list = []
            for item in db_value:
                if isinstance(item, dict) and 'name' in item:
                    processed_list.append(str(item['name']))
                elif isinstance(item, str):
                    processed_list.append(item)
                elif item is not None: # Для других типов (числа, булевы)
                    processed_list.append(str(item))
            display_values_for_form[key] = processed_list
        elif isinstance(db_value, dict):
            # Если это старый формат {'name': X, 'wikidata': Y} для поля, которое теперь простое,
            # извлекаем X. Иначе, если это предполагаемый объект, передаем как есть (пока не поддерживается сложная логика объектов).
            # Для упрощения, если словарь имеет ключ 'name', предполагаем, что его значение основное.
            if 'name' in db_value: #  and 'wikidata' in db_value: # Убрал 'wikidata' для более общего случая
                display_values_for_form[key] = str(db_value['name'])
            else:
                # Если это сложный объект без 'name', его нужно будет обрабатывать отдельно в шаблоне
                # или передать как JSON-строку, если нет специального рендеринга.
                # Пока что, для неизвестных словарей, преобразуем в строку или пропускаем.
                # Чтобы избежать ошибок в шаблоне, лучше преобразовать в строку.
                display_values_for_form[key] = json.dumps(db_value, ensure_ascii=False) # или str(db_value)
        elif db_value is not None: # Простые значения (строки, числа, булевы)
            display_values_for_form[key] = str(db_value)
        # None значения пропускаем, они не должны создавать поля в форме

    # Отладочный вывод - посмотрим, что получилось после преобразования
    logger.debug(f"DISPLAY VALUES FOR FORM: {display_values_for_form}")
    
    metadata_with_types = {}
    for key, form_value in display_values_for_form.items():
        if isinstance(form_value, list):
            metadata_with_types[key] = {'value': form_value, 'type': 'array'}
        # После предыдущей обработки, form_value для простых полей должен быть строкой.
        # Объекты (сложные словари) требуют отдельного типа 'object' если мы их поддерживаем.
        elif isinstance(form_value, dict): # Должно быть редкостью после обработки выше
             metadata_with_types[key] = {'value': form_value, 'type': 'object'}
        else: # Строки, числа (приведенные к строкам)
            metadata_with_types[key] = {'value': form_value, 'type': 'simple'}
    
    # Отладочный вывод - посмотрим, что получилось после преобразования типов
    logger.debug(f"METADATA WITH TYPES: {metadata_with_types}")
            
    from django.db.models import Count
    entity_categories = document.entity_relations.values('field_category').annotate(count=Count('id'))
    entities_by_category = {}
    for category in entity_categories:
        cat_name = category['field_category']
        if cat_name:
            entities_by_category[cat_name] = document.entity_relations.filter(
                field_category=cat_name
            ).select_related('entity').order_by('-confidence')
    
    
    return render(request, 'enhancer/document_detail.html', {
        'document': document,
        'metadata': json.dumps(raw_metadata, ensure_ascii=False),  # Для отображения в JSON-редакторе
        'metadata_with_types': metadata_with_types,
        'file_size': file_size,
        'entities_by_category': entities_by_category,
    })

@csrf_protect
def wikidata_search(request):
    """
    API для поиска сущностей в Wikidata
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    query = request.GET.get('query', '')
    entity_type = request.GET.get('type', '')
    
    if not query:
        return JsonResponse({'error': 'Необходимо указать поисковый запрос'}, status=400)
    
    try:
        from apps.enhancer.processing.wikidata import link_to_wikidata
        import time
        import requests
        
        headers = {
            "User-Agent": "DocsMetadataEnhancerBot/1.0 (https://example.com; zheny@example.com)"
        }
        
        # Поиск через wbsearchentities
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            "action": "wbsearchentities",
            "search": query,
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
            return JsonResponse({'results': []})
        
        # Фильтрация по типу сущности, если указан
        results = []
        for result in search_results:
            results.append({
                'id': result.get('id'),
                'label': result.get('label', ''),
                'description': result.get('description', '')
            })
        
        if results:
            return JsonResponse({'results': results})
        else:
            return JsonResponse({'results': []})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_protect
def update_document_wikidata(request, document_id):
    """
    Обновляет все связи документа с Wikidata
    """
    # Проверяем, что метод запроса поддерживается
    if request.method != 'GET' and request.method != 'POST':
        return JsonResponse({
            'success': False, 
            'error': f'Метод {request.method} не поддерживается, используйте GET или POST',
            'message': 'Ошибка при обновлении связей'
        }, status=405)
        
    document = get_object_or_404(Document, id=document_id, owner=request.user)
    
    try:
        from apps.enhancer.processing.wikidata_orm import update_document_wikidata_links
        
        # Фиксируем количество связей до обновления
        old_relations_count = document.entity_relations.count()
        
        # Обновляем связи с Wikidata
        new_links_count = update_document_wikidata_links(document)
        
        # Собираем статистику по категориям
        from django.db.models import Count
        entity_stats = document.entity_relations.values('field_category').annotate(count=Count('id'))
        
        category_stats = {}
        for stat in entity_stats:
            category_stats[stat['field_category']] = stat['count']
        
        # Полностью обновляем фрагмент с сущностями
        from django.template.loader import render_to_string
        
        # Группируем сущности по категориям для удобного отображения
        entity_categories = document.entity_relations.values('field_category').annotate(count=Count('id'))
        entities_by_category = {}
        for category in entity_categories:
            cat_name = category['field_category']
            if cat_name:  # Проверка на None
                entities_by_category[cat_name] = document.entity_relations.filter(
                    field_category=cat_name
                ).select_related('entity').order_by('-confidence')
            
        # Рендерим HTML-фрагмент с обновленными данными
        html_fragment = render_to_string('enhancer/fragments/wikidata_entities.html', {
            'document': document,
            'entities_by_category': entities_by_category
        }, request=request)
        
        total_count = document.entity_relations.count()
        
        return JsonResponse({
            'success': True, 
            'message': f'Обновлено {new_links_count} связей с Wikidata',
            'html_fragment': html_fragment,
            'stats': {
                'total': total_count,
                'new': new_links_count,
                'by_category': category_stats
            }
        })
    except Exception as e:
        import traceback
        logger.error(f"Ошибка при обновлении связей с Wikidata: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False, 
            'error': str(e),
            'message': 'Произошла ошибка при обновлении связей',
            'traceback': traceback.format_exc()
        }, status=500)

@csrf_protect
def link_entity_to_document(request, document_id):
    """
    Связывает сущность Wikidata с документом
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    document = get_object_or_404(Document, id=document_id, owner=request.user)
    
    try:
        # Проверяем формат данных в зависимости от типа запроса
        if request.headers.get('Content-Type') == 'application/json':
            data = json.loads(request.body)
            entity_name = data.get('entity_name')
            entity_id = data.get('entity_id')
            category = data.get('category')
            entity_type = data.get('entity_type')
            field_key = data.get('field_key')
            field_value = data.get('field_value')
        else:
            entity_name = request.POST.get('entity_name')
            entity_id = request.POST.get('entity_id')
            category = request.POST.get('category')
            entity_type = request.POST.get('entity_type')
            field_key = request.POST.get('field_key')
            field_value = request.POST.get('field_value')
        
        if not category:
            return JsonResponse({'error': 'Категория обязательна', 'success': False}, status=400)
        
        # Если указаны поля field_key и field_value, используем их
        # Иначе используем категорию как field_key, а имя сущности как field_value
        actual_field_key = field_key if field_key else category
        actual_field_value = field_value if field_value else entity_name
        
        from apps.enhancer.processing.wikidata_orm import search_and_link_entity_to_document, get_or_create_wikidata_entity
        
        if entity_id:
            entity = get_or_create_wikidata_entity(entity_id, entity_name)
            
            # Создаем или обновляем связь с учетом новых полей
            relation, created = DocumentEntityRelation.objects.get_or_create(
                document=document,
                entity=entity,
                field_category=category,
                field_key=actual_field_key,
                field_value=actual_field_value,
                defaults={
                    "name": entity_name,  # Для обратной совместимости
                    "confidence": 1.0,
                    "context": f"Manually added to {category}, field: {actual_field_key}"
                }
            )
            
            # Обновляем meta_wikidata документа, чтобы отразить связь
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
            
            success = True
            message = 'Сущность успешно связана с документом'
        elif entity_name:
            # Здесь должна быть логика поиска и связывания по имени
            # Но она более сложная и должна быть адаптирована под новую модель
            relation = search_and_link_entity_to_document(document, entity_name, category, entity_type, 
                                                      field_key=actual_field_key, field_value=actual_field_value)
            if relation:
                success = True
                message = 'Сущность успешно найдена и связана с документом'
            else:
                success = False
                message = 'Не удалось найти подходящую сущность в Wikidata'
                return JsonResponse({'success': False, 'message': message})
        else:
            return JsonResponse({'error': 'Необходимо указать имя или ID сущности', 'success': False}, status=400)
        
        return JsonResponse({'success': success, 'message': message})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def wikidata_entity_info(request, qid):
    """
    API для получения информации о сущности Wikidata
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    try:
        from apps.enhancer.processing.wikidata_orm import fetch_wikidata_entity, get_or_create_wikidata_entity
        
        # Проверяем кэш и базу данных
        entity = WikidataEntity.objects.filter(qid=qid).first()
        
        # Если сущность есть в БД, возвращаем её данные
        if entity:
            return JsonResponse({
                'id': entity.qid,
                'label_ru': entity.label_ru,
                'label_en': entity.label_en,
                'description_ru': entity.description_ru,
                'description_en': entity.description_en,
                'properties': entity.properties,
                'source': 'database'
            })
        
        # Если сущности нет в БД, получаем данные из Wikidata
        try:
            entity_data = fetch_wikidata_entity(qid)
        except Exception as e:
            return JsonResponse({'error': f'Ошибка при загрузке данных из Wikidata: {str(e)}'}, status=500)
        
        if not entity_data:
            return JsonResponse({'error': 'Сущность не найдена'}, status=404)
        
        # Создаем сущность в БД для кэширования
        entity = get_or_create_wikidata_entity(qid, entity_data.get('label_ru', entity_data.get('label_en', qid)))
        
        # Формируем ответ
        return JsonResponse({
            'id': qid,
            'label_ru': entity_data.get('label_ru', ''),
            'label_en': entity_data.get('label_en', ''),
            'description_ru': entity_data.get('description_ru', ''),
            'description_en': entity_data.get('description_en', ''),
            'properties': entity_data.get('properties', {}),
            'source': 'wikidata_api'
        })
        
    except Exception as e:
        import traceback
        return JsonResponse({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)

@csrf_protect
def unlink_entity_from_document(request, document_id):
    """
    Отвязывает сущность Wikidata от документа
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)
    
    document = get_object_or_404(Document, id=document_id, owner=request.user)
    
    try:
        # Получаем данные из запроса
        if request.headers.get('Content-Type') == 'application/json':
            data = json.loads(request.body)
            entity_id = data.get('entity_id')
            relation_id = data.get('relation_id')
            category = data.get('category')
            field_key = data.get('field_key')
            field_value = data.get('field_value')
            bulk_mode = data.get('bulk_mode', False)  # Режим массового удаления связей
        else:
            entity_id = request.POST.get('entity_id')
            relation_id = request.POST.get('relation_id')
            category = request.POST.get('category')
            field_key = request.POST.get('field_key')
            field_value = request.POST.get('field_value')
            bulk_mode = request.POST.get('bulk_mode') == 'true'  # Для form-data
        
        # Журналирование для отладки
        logger.debug(f"Запрос на отвязывание сущности: entity_id={entity_id}, relation_id={relation_id}, category={category}, field_key={field_key}, field_value={field_value}, bulk_mode={bulk_mode}")
        
        # Проверяем наличие необходимых параметров
        if not (entity_id or relation_id or (category and field_key)):
            return JsonResponse({
                'success': False, 
                'error': 'Необходимо указать ID сущности или ID связи, либо категорию и ключ поля'
            }, status=400)
        
        # Готовим переменные для ответа и обновления meta_wikidata
        entity = None
        relation_category = None
        actual_field_key = None
        actual_field_value = None
        affected_relations = 0
        
        if relation_id:
            # Если указан ID связи, удаляем её
            try:
                relation = DocumentEntityRelation.objects.get(
                    id=relation_id,
                    document=document
                )
                entity = relation.entity
                relation_category = relation.field_category
                actual_field_key = relation.field_key
                actual_field_value = relation.field_value
                
                # Удаляем связь
                relation.delete()
                affected_relations += 1
                
                # Проверяем, остались ли другие связи с этой сущностью
                if not DocumentEntityRelation.objects.filter(document=document, entity=entity).exists():
                    document.entity_relations.filter(entity=entity).delete()
                
            except DocumentEntityRelation.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'Связь не найдена'
                }, status=404)
        
        elif entity_id and (category or field_key):
            # Формируем запрос на основе переданных параметров
            relation_query = {
                'document': document
            }
            
            try:
                # Если указан ID сущности, добавляем его в запрос
                if entity_id:
                    entity = WikidataEntity.objects.get(qid=entity_id)
                    relation_query['entity'] = entity
                
                # Добавляем дополнительные фильтры, если они переданы
                if category:
                    relation_query['field_category'] = category
                if field_key:
                    relation_query['field_key'] = field_key
                if field_value and not bulk_mode:
                    relation_query['field_value'] = field_value
                
                # В режиме массового удаления или если запрос по конкретным параметрам
                if bulk_mode:
                    # Получаем все связи, соответствующие фильтрам
                    relations = DocumentEntityRelation.objects.filter(**relation_query)
                    if not relations.exists():
                        return JsonResponse({
                            'success': False, 
                            'error': 'Связи не найдены'
                        }, status=404)
                    
                    # Запоминаем информацию для формирования ответа
                    if relations.count() > 0:
                        first_relation = relations.first()
                        relation_category = first_relation.field_category
                        actual_field_key = first_relation.field_key
                        if entity is None and first_relation.entity:
                            entity = first_relation.entity
                    
                    # Подсчитываем количество удаляемых связей
                    affected_relations = relations.count()
                    
                    # Удаляем все связи
                    relations.delete()
                else:
                    # Ищем конкретную связь
                    try:
                        relation = DocumentEntityRelation.objects.get(**relation_query)
                        
                        entity = relation.entity
                        relation_category = relation.field_category
                        actual_field_key = relation.field_key
                        actual_field_value = relation.field_value
                        
                        # Удаляем связь
                        relation.delete()
                        affected_relations += 1
                    except DocumentEntityRelation.DoesNotExist:
                        return JsonResponse({
                            'success': False, 
                            'error': 'Связь не найдена по указанным параметрам'
                        }, status=404)
                
                # Проверяем, остались ли другие связи с этой сущностью
                if entity and not DocumentEntityRelation.objects.filter(document=document, entity=entity).exists():
                    document.entity_relations.filter(entity=entity).delete()
                
            except WikidataEntity.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'Сущность Wikidata не найдена'
                }, status=404)
        
        else:
            return JsonResponse({
                'success': False, 
                'error': 'Недостаточно параметров для выполнения операции'
            }, status=400)
        
        # Обновляем meta_wikidata, если у нас есть необходимая информация
        if entity and actual_field_key:
            meta_wikidata = document.meta_wikidata or {}
            
            if actual_field_key in meta_wikidata:
                # Если поле - словарь и у нас есть конкретное значение
                if isinstance(meta_wikidata[actual_field_key], dict) and actual_field_value and not bulk_mode:
                    if actual_field_value in meta_wikidata[actual_field_key]:
                        del meta_wikidata[actual_field_key][actual_field_value]
                
                # Если поле - словарь и мы в режиме массового удаления
                elif isinstance(meta_wikidata[actual_field_key], dict) and bulk_mode:
                    # Удаляем все значения, связанные с данной сущностью
                    keys_to_remove = []
                    for key, qid in meta_wikidata[actual_field_key].items():
                        if qid == entity.qid:
                            keys_to_remove.append(key)
                    
                    for key in keys_to_remove:
                        del meta_wikidata[actual_field_key][key]
                
                # Если поле - список
                elif isinstance(meta_wikidata[actual_field_key], list):
                    # Удаляем пары [value, qid], где qid совпадает
                    to_remove = []
                    for i, item in enumerate(meta_wikidata[actual_field_key]):
                        if isinstance(item, list) and len(item) > 1 and item[1] == entity.qid:
                            # В режиме не массового удаления проверяем значение
                            if bulk_mode or not actual_field_value or item[0] == actual_field_value:
                                to_remove.append(i)
                        elif isinstance(item, dict) and item.get('qid') == entity.qid:
                            # В режиме не массового удаления проверяем значение
                            if bulk_mode or not actual_field_value or item.get('value') == actual_field_value:
                                to_remove.append(i)
                    
                    # Удаляем элементы с конца списка, чтобы не нарушить индексацию
                    for i in sorted(to_remove, reverse=True):
                        meta_wikidata[actual_field_key].pop(i)
            
            # Сохраняем изменения
            document.meta_wikidata = meta_wikidata
            document.save(update_fields=['meta_wikidata'])
        
        # Формируем сообщение об успехе в зависимости от режима
        if bulk_mode:
            message = f'Удалено {affected_relations} связей'
            if entity:
                message += f' с сущностью {entity.label_ru or entity.label_en or entity.qid}'
            if category:
                message += f' в категории {category}'
        else:
            entity_name = entity.label_ru or entity.label_en or entity.qid if entity else "неизвестной сущности"
            message = f'Связь с сущностью {entity_name} успешно удалена'
        
        return JsonResponse({
            'success': True, 
            'message': message,
            'entity_id': entity.qid if entity else None,
            'category': relation_category,
            'field_key': actual_field_key,
            'field_value': actual_field_value,
            'affected_count': affected_relations,
            'bulk_mode': bulk_mode
        })
        
    except Exception as e:
        import traceback
        logger.error(f"Ошибка при отвязывании сущности: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)

def update_entity_relations_from_meta_wikidata(document):
    """
    Обновляет связи DocumentEntityRelation на основе meta_wikidata
    """
    from .models import WikidataEntity, DocumentEntityRelation
    
    if not document.meta_wikidata:
        return
    
    # Словарь для отслеживания созданных связей
    created_relations = set()
    
    # Обрабатываем каждое поле в meta_wikidata
    for field_key, field_data in document.meta_wikidata.items():
        # Преобразуем field_name в категорию поля для DocumentEntityRelation
        field_category = convert_field_to_category(field_key)
        
        # Если field_data - словарь (item_value: qid)
        if isinstance(field_data, dict):
            for item_value, qid in field_data.items():
                if not qid:
                    continue
                    
                # Получаем или создаем сущность Wikidata
                entity, _ = WikidataEntity.objects.get_or_create(
                    qid=qid,
                    defaults={
                        'label_ru': item_value,
                    }
                )
                
                # Создаем или обновляем связь
                relation, created = DocumentEntityRelation.objects.update_or_create(
                    document=document,
                    entity=entity,
                    field_category=field_category,
                    field_key=field_key,
                    field_value=item_value,
                    defaults={
                        'name': item_value,  # Сохраняем для обратной совместимости
                        'confidence': 1.0,
                        'context': f'From metadata field: {field_key}'
                    }
                )
                
                # Добавляем в отслеживаемые связи
                relation_key = (field_category, entity.qid, field_key, item_value)
                created_relations.add(relation_key)
        
        # Если field_data - список пар [item_value, qid]
        elif isinstance(field_data, list):
            for item in field_data:
                # Проверяем формат элемента (может быть строкой qid или списком [item_value, qid])
                if isinstance(item, list) and len(item) == 2:
                    item_value, qid = item
                elif isinstance(item, dict) and 'value' in item and 'qid' in item:
                    item_value, qid = item['value'], item['qid']
                else:
                    # Если это просто значение без QID, пропускаем
                    continue
                
                if not qid:
                    continue
                    
                # Получаем или создаем сущность Wikidata
                entity, _ = WikidataEntity.objects.get_or_create(
                    qid=qid,
                    defaults={
                        'label_ru': item_value if isinstance(item_value, str) else str(item_value),
                    }
                )
                
                str_item_value = item_value if isinstance(item_value, str) else str(item_value)
                
                # Создаем связь
                relation, created = DocumentEntityRelation.objects.update_or_create(
                    document=document,
                    entity=entity,
                    field_category=field_category,
                    field_key=field_key,
                    field_value=str_item_value,
                    defaults={
                        'name': str_item_value,  # Сохраняем для обратной совместимости
                        'confidence': 1.0,
                        'context': f'From metadata field: {field_key}'
                    }
                )
                
                # Добавляем в отслеживаемые связи
                relation_key = (field_category, entity.qid, field_key, str_item_value)
                created_relations.add(relation_key)
    
    # Удаляем связи, которые больше не существуют в meta_wikidata
    existing_relations = DocumentEntityRelation.objects.filter(document=document)
    for relation in existing_relations:
        relation_key = (relation.field_category, relation.entity.qid, relation.field_key, relation.field_value)
        if relation_key not in created_relations:
            relation.delete()
    
    return len(created_relations)

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

@csrf_protect
def refresh_entity_descriptions(request, document_id):
    """
    Обновляет описания всех сущностей документа из Wikidata
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Метод не поддерживается'}, status=405)
    
    document = get_object_or_404(Document, id=document_id, owner=request.user)
    
    try:
        from apps.enhancer.processing.wikidata_orm import fetch_wikidata_entity
        
        # Получаем все уникальные сущности, связанные с документом
        entities = WikidataEntity.objects.filter(
            document_relations__document=document
        ).distinct()
        
        updated_count = 0
        not_found_count = 0
        
        # Обновляем описания каждой сущности
        for entity in entities:
            entity_data = fetch_wikidata_entity(entity.qid)
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
                updated_count += 1
            else:
                not_found_count += 1
        
        # Генерируем HTML-фрагмент с обновленными сущностями
        from django.template.loader import render_to_string
        
        # Группируем сущности по категориям
        from django.db.models import Count
        entity_categories = document.entity_relations.values('field_category').annotate(count=Count('id'))
        entities_by_category = {}
        for category in entity_categories:
            cat_name = category['field_category']
            if cat_name:
                entities_by_category[cat_name] = document.entity_relations.filter(
                    field_category=cat_name
                ).select_related('entity').order_by('-confidence')
        
        # Рендерим HTML-фрагмент с обновленными данными
        html_fragment = render_to_string('enhancer/fragments/wikidata_entities.html', {
            'document': document,
            'entities_by_category': entities_by_category
        }, request=request)
        
        # Формируем сообщение
        message = f'Обновлено описаний: {updated_count}'
        if not_found_count > 0:
            message += f', не найдено: {not_found_count}'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'html_fragment': html_fragment,
            'updated_count': updated_count,
            'not_found_count': not_found_count
        })
    
    except Exception as e:
        import traceback
        logger.error(f"Ошибка при обновлении описаний сущностей: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)

@csrf_protect
def document_rename(request, document_id):
    """
    Переименовывает документ
    """
    if request.method == 'POST':
        new_name = request.POST.get('name')
        
        if not new_name:
            messages.error(request, "Название документа не может быть пустым")
            return redirect('enhancer:file_system')
        
        try:
            document = get_object_or_404(Document, id=document_id, owner=request.user)
            old_name = document.name
            document.name = new_name
            document.save()
            
            # Формируем сообщение об успешном переименовании
            messages.success(request, f"Документ '{old_name}' переименован в '{new_name}'")
            
            # Перенаправляем на страницу папки документа или на главную страницу
            if document.folder:
                return redirect('enhancer:folder_detail', folder_id=document.folder.id)
            else:
                return redirect('enhancer:file_system')
            
        except Exception as e:
            logger.error(f"Ошибка при переименовании документа: {str(e)}", exc_info=True)
            messages.error(request, f"Ошибка при переименовании документа: {str(e)}")
            # Перенаправляем на главную страницу файловой системы
            return redirect('enhancer:file_system')
    
    # Если метод не POST, перенаправляем на главную страницу
    return redirect('enhancer:file_system')

@csrf_protect
def document_delete(request, document_id):
    """
    Удаляет документ
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, owner=request.user)
            name = document.name
            file_type = document.file_type
            
            # Получаем папку документа перед удалением для последующего перенаправления
            folder = document.folder
            
            # Удаляем документ (это также удаляет связанный файл)
            document.delete()
            
            # Формируем сообщение об успешном удалении
            messages.success(request, f"Документ '{name}.{file_type}' успешно удален")
            
            # Перенаправляем на страницу папки или на главную, если папки нет
            if folder:
                return redirect('enhancer:folder_detail', folder_id=folder.id)
            return redirect('enhancer:file_system')
            
        except Exception as e:
            logger.error(f"Ошибка при удалении документа: {str(e)}", exc_info=True)
            messages.error(request, f"Ошибка при удалении документа: {str(e)}")
            return redirect('enhancer:file_system')
    
    # Если метод не POST, перенаправляем на главную страницу
    return redirect('enhancer:file_system')

def document_download(request, document_id):
    """
    Скачивание документа
    """
    document = get_object_or_404(Document, id=document_id, owner=request.user)
    
    try:
        if not document.file:
            messages.error(request, "Файл не найден")
            return redirect('enhancer:document_detail', document_id=document_id)
        
        file_path = document.file.path
        
        if not os.path.exists(file_path):
            messages.error(request, "Файл не найден на диске")
            return redirect('enhancer:document_detail', document_id=document_id)
        
        # Получаем имя файла для скачивания
        filename = f"{document.name}.{document.file_type}"
        
        # Открываем файл и создаем FileResponse
        response = FileResponse(open(file_path, 'rb'))
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании документа: {str(e)}", exc_info=True)
        messages.error(request, f"Ошибка при скачивании документа: {str(e)}")
        return redirect('enhancer:document_detail', document_id=document_id)

def document_export(request, document_id):
    """
    Экспортирует документ с метаданными в различных форматах
    
    Параметры запроса:
    - format: json или xml (формат метаданных)
    - include_wikidata: 1 или 0 (включать ли данные из Wikidata)
    - export_type: zip, metadata_only или pdf_embedded (тип экспорта)
    """
    document = get_object_or_404(Document, id=document_id, owner=request.user)
    
    # Получаем параметры экспорта
    metadata_format = request.GET.get('format', 'json')
    include_wikidata = request.GET.get('include_wikidata', '1') == '1'
    export_type = request.GET.get('export_type', 'zip')
    
    try:
        # Подготовка метаданных для экспорта
        metadata = document.metadata or {}
        
        # Если нужно включить данные из Wikidata
        if include_wikidata:
            # Создаем словарь для быстрого поиска связей по ключу и значению
            wikidata_relations = {}
            
            # Получаем все связи документа с сущностями
            entity_relations = document.entity_relations.select_related('entity').all()
            
            # Строим словарь связей
            for relation in entity_relations:
                entity = relation.entity
                field_key = relation.field_key
                field_value = relation.field_value
                
                # Создаем ключ для словаря связей
                relation_key = (field_key, field_value)
                
                # Если ключа еще нет, инициализируем
                if relation_key not in wikidata_relations:
                    wikidata_relations[relation_key] = []
                
                # Добавляем информацию о сущности
                wikidata_relations[relation_key].append({
                    'qid': entity.qid,
                    'label_ru': entity.label_ru,
                    'label_en': entity.label_en,
                    'description_ru': entity.description_ru,
                    'description_en': entity.description_en
                })
            
            # Преобразуем метаданные, включая информацию из Wikidata
            new_metadata = {}
            for key, value in metadata.items():
                # Обрабатываем массивы
                if isinstance(value, list):
                    new_values = []
                    for item in value:
                        if isinstance(item, str):
                            # Проверяем, есть ли для этого элемента связь с Wikidata
                            relation_key = (key, item)
                            if relation_key in wikidata_relations:
                                # Берем первую связь (обычно должна быть одна)
                                entity_info = wikidata_relations[relation_key][0]
                                
                                # Формируем новый элемент с данными Wikidata
                                new_item = [
                                    entity_info.get('label_ru') or item,  # Используем метку на русском или исходное значение
                                    {"label_en": entity_info.get('label_en', '')},
                                    {"wikidata_q": entity_info.get('qid', '')},
                                    {"description_ru": entity_info.get('description_ru', '')},
                                    {"description_en": entity_info.get('description_en', '')}
                                ]
                                new_values.append(new_item)
                            else:
                                # Если нет связи, оставляем как есть
                                new_values.append(item)
                        else:
                            # Если элемент не строка, оставляем как есть
                            new_values.append(item)
                    new_metadata[key] = new_values
                
                # Обрабатываем простые поля (строки)
                elif isinstance(value, str):
                    relation_key = (key, value)
                    if relation_key in wikidata_relations:
                        # Берем первую связь
                        entity_info = wikidata_relations[relation_key][0]
                        
                        # Формируем новый элемент с данными Wikidata
                        new_value = [
                            entity_info.get('label_ru') or value,  # Используем метку на русском или исходное значение
                            {"label_en": entity_info.get('label_en', '')},
                            {"wikidata_q": entity_info.get('qid', '')},
                            {"description_ru": entity_info.get('description_ru', '')},
                            {"description_en": entity_info.get('description_en', '')}
                        ]
                        new_metadata[key] = new_value
                    else:
                        # Если нет связи, оставляем как есть
                        new_metadata[key] = value
                
                # Сохраняем остальные типы данных как есть
                else:
                    new_metadata[key] = value
            
            # Заменяем исходные метаданные на преобразованные
            metadata = new_metadata
            
            # # Сохраняем оригинальные связи Wikidata для обратной совместимости или справочной информации
            # wikidata_entities = {}
            # for relation in entity_relations:
            #     entity = relation.entity
            #     if entity.qid not in wikidata_entities:
            #         wikidata_entities[entity.qid] = {
            #             'id': entity.qid,
            #             'label_ru': entity.label_ru,
            #             'label_en': entity.label_en,
            #             'description_ru': entity.description_ru,
            #             'description_en': entity.description_en,
            #             'properties': entity.properties,
            #             'relations': []
            #         }
                
            #     # Добавляем информацию о связи
            #     wikidata_entities[entity.qid]['relations'].append({
            #         'field_category': relation.field_category,
            #         'field_key': relation.field_key,
            #         'field_value': relation.field_value,
            #         'confidence': relation.confidence
            #     })
            
            # # Сохраняем полную информацию о сущностях в отдельное поле для справки
            # metadata['_wikidata_entities_full'] = wikidata_entities
        
        # Формируем структуру экспортируемых данных
        export_data = {
            'document': {
                'id': document.id,
                'name': document.name,
                'file_type': document.file_type,
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat()
            },
            'metadata': metadata
        }
        
        # Если нужно включить сырые данные о Wikidata
        if include_wikidata and document.meta_wikidata:
            export_data['_wikidata_links_raw'] = document.meta_wikidata
        
        # Выбираем действие в зависимости от типа экспорта
        if export_type == 'metadata_only':
            # Экспорт только метаданных (без документа)
            if metadata_format == 'json':
                # Экспорт в JSON
                response = HttpResponse(
                    json.dumps(export_data, ensure_ascii=False, indent=2),
                    content_type='application/json'
                )
                response['Content-Disposition'] = f'attachment; filename="{document.name}_metadata.json"'
                return response
            elif metadata_format == 'xml':
                # Экспорт в XML
                try:
                    import dicttoxml
                    from xml.dom.minidom import parseString
                    
                    xml_data = dicttoxml.dicttoxml(export_data, custom_root='document_metadata', attr_type=False)
                    dom = parseString(xml_data)
                    pretty_xml = dom.toprettyxml()
                    
                    response = HttpResponse(pretty_xml, content_type='application/xml')
                    response['Content-Disposition'] = f'attachment; filename="{document.name}_metadata.xml"'
                    return response
                except ImportError:
                    messages.error(request, "Не удалось создать XML. Библиотека dicttoxml не установлена.")
                    return redirect('enhancer:document_detail', document_id=document.id)
        
        elif export_type == 'pdf_embedded' and document.file_type.lower() == 'pdf':
            # Встраивание метаданных в PDF (только для PDF)
            try:
                import io
                from PyPDF2 import PdfReader, PdfWriter
                
                # Получаем метаданные в нужном формате
                if metadata_format == 'json':
                    metadata_str = json.dumps(export_data, ensure_ascii=False)
                else:  # xml
                    import dicttoxml
                    from xml.dom.minidom import parseString
                    
                    xml_data = dicttoxml.dicttoxml(export_data, custom_root='document_metadata', attr_type=False)
                    dom = parseString(xml_data)
                    metadata_str = dom.toprettyxml()
                
                # Читаем исходный PDF
                with open(document.file.path, 'rb') as pdf_file:
                    reader = PdfReader(pdf_file)
                    writer = PdfWriter()
                    
                    # Копируем все страницы
                    for page in reader.pages:
                        writer.add_page(page)
                    
                    # Добавляем метаданные
                    writer.add_metadata({
                        '/Title': document.name,
                        '/Subject': 'Document with embedded metadata',
                        '/Author': request.user.username,
                        '/Creator': 'Docs Metadata Enhancer',
                        '/Producer': 'Docs Metadata Enhancer',
                        '/Metadata': metadata_str
                    })
                    
                    # Записываем в буфер
                    buffer = io.BytesIO()
                    writer.write(buffer)
                    buffer.seek(0)
                    
                    # Возвращаем PDF
                    response = HttpResponse(buffer, content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="{document.name}_with_metadata.pdf"'
                    return response
                    
            except ImportError:
                messages.error(request, "Не удалось встроить метаданные в PDF. Отсутствуют необходимые библиотеки (PyPDF2).")
                return redirect('enhancer:document_detail', document_id=document.id)
        
        else:  # export_type == 'zip' (по умолчанию)
            # Создаем ZIP-архив с документом и метаданными
            try:
                import zipfile
                import io
                
                # Создаем буфер для ZIP
                buffer = io.BytesIO()
                
                # Создаем ZIP-архив
                with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                    # Добавляем документ
                    with open(document.file.path, 'rb') as doc_file:
                        zip_file.writestr(f"{document.name}.{document.file_type}", doc_file.read())
                    
                    # Добавляем метаданные в выбранном формате
                    if metadata_format == 'json':
                        metadata_str = json.dumps(export_data, ensure_ascii=False, indent=2)
                        zip_file.writestr(f"{document.name}_metadata.json", metadata_str.encode('utf-8'))
                    else:  # xml
                        import dicttoxml
                        from xml.dom.minidom import parseString
                        
                        xml_data = dicttoxml.dicttoxml(export_data, custom_root='document_metadata', attr_type=False)
                        dom = parseString(xml_data)
                        pretty_xml = dom.toprettyxml()
                        zip_file.writestr(f"{document.name}_metadata.xml", pretty_xml.encode('utf-8'))
                
                # Возвращаем ZIP-архив
                buffer.seek(0)
                response = HttpResponse(buffer.getvalue(), content_type='application/zip')
                response['Content-Disposition'] = f'attachment; filename="{document.name}_with_metadata.zip"'
                return response
                
            except ImportError:
                messages.error(request, "Не удалось создать ZIP-архив. Отсутствуют необходимые библиотеки.")
                return redirect('enhancer:document_detail', document_id=document.id)
    
    except Exception as e:
        logger.error(f"Ошибка при экспорте документа: {str(e)}", exc_info=True)
        messages.error(request, f"Ошибка при экспорте документа: {str(e)}")
        return redirect('enhancer:document_detail', document_id=document.id)
    
    # Если ничего не вернулось выше, редиректим на детали документа
    return redirect('enhancer:document_detail', document_id=document.id)