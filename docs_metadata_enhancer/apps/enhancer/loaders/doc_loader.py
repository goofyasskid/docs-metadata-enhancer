import os
import logging
import traceback
import subprocess
import tempfile
from langchain_community.document_loaders import TextLoader

# Настройка логирования
logger = logging.getLogger(__name__)

def load_doc(doc_path):
    """
    Загружает и обрабатывает DOC документ (старый формат Word)
    Args:
        doc_path (str): Путь к DOC файлу
    Returns:
        list: Список объектов Document, содержащих текст документа и метаданные
    """
    try:
        logger.info(f"Начало загрузки DOC: {doc_path}")
        
        # Проверка существования файла
        if not os.path.exists(doc_path):
            error_msg = f"DOC файл не найден по пути: {doc_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        # Получение абсолютного пути
        abs_path = os.path.abspath(doc_path)
        logger.info(f"Абсолютный путь к файлу: {abs_path}")
        
        # Проверка расширения файла
        _, ext = os.path.splitext(abs_path)
        if ext.lower() != '.doc':
            error_msg = f"Файл должен быть в формате DOC, получен формат: {ext}"
            logger.error(error_msg)
            return None
        
        # Проверка размера файла
        file_size = os.path.getsize(abs_path) / (1024 * 1024)  # в МБ
        logger.info(f"Размер файла: {file_size:.2f} МБ")
        
        # Для DOC используем конвертацию через LibreOffice или MS Word
        # Создаем временный файл для хранения текста
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Пытаемся использовать LibreOffice
            logger.info(f"Попытка конвертации с помощью LibreOffice")
            subprocess.run(
                ['soffice', '--headless', '--convert-to', 'txt', abs_path, '--outdir', os.path.dirname(temp_path)],
                check=True, capture_output=True
            )
            
            # Переименовываем выходной файл, если он имеет другое имя
            base_name = os.path.basename(abs_path)
            converted_name = os.path.splitext(base_name)[0] + '.txt'
            converted_path = os.path.join(os.path.dirname(temp_path), converted_name)
            
            if os.path.exists(converted_path):
                os.rename(converted_path, temp_path)
            else:
                raise FileNotFoundError(f"Не удалось найти конвертированный файл: {converted_path}")
                
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"Не удалось использовать LibreOffice: {str(e)}")
            
            try:
                # Альтернативно, пытаемся использовать antiword
                logger.info(f"Попытка конвертации с помощью antiword")
                with open(temp_path, 'w', encoding='utf-8') as f:
                    subprocess.run(['antiword', abs_path], stdout=f, check=True, capture_output=True)
            except (subprocess.SubprocessError, FileNotFoundError) as e:
                logger.warning(f"Не удалось использовать antiword: {str(e)}")
                
                try:
                    # Последняя попытка - использовать catdoc
                    logger.info(f"Попытка конвертации с помощью catdoc")
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        subprocess.run(['catdoc', abs_path], stdout=f, check=True, capture_output=True)
                except (subprocess.SubprocessError, FileNotFoundError) as e:
                    logger.error(f"Не удалось конвертировать DOC файл: {str(e)}")
                    os.unlink(temp_path)
                    return None
        
        # Загружаем конвертированный текст
        logger.info(f"Загрузка конвертированного текста с помощью TextLoader")
        loader = TextLoader(temp_path, encoding='utf-8')
        documents = loader.load()
        
        # Удаляем временный файл
        os.unlink(temp_path)
        
        if not documents:
            logger.error("TextLoader вернул пустой список документов")
            return None
            
        logger.info(f"DOC успешно загружен. Количество документов: {len(documents)}")
        
        # Проверка содержимого
        if documents and hasattr(documents[0], 'page_content'):
            content_sample = documents[0].page_content[:100].replace('\n', ' ')
            logger.info(f"Пример содержимого: '{content_sample}...'")
        
        return documents
    
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при загрузке DOC: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None

if __name__ == "__main__":
    # Используйте относительный путь от текущего каталога
    current_dir = os.path.dirname(os.path.abspath(__file__))
    doc_path = os.path.join(current_dir, "..", "sources", "example.doc")
    
    documents = load_doc(doc_path)
    if documents:
        print(f"Успешно загружено {len(documents)} документов")
        print("\nПример содержимого:")
        print("=" * 50)
        print(documents[0].page_content[:1000])
        print("=" * 50) 