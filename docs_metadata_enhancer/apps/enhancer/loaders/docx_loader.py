import os
import logging
import traceback
from langchain_community.document_loaders import Docx2txtLoader

# Настройка логирования
logger = logging.getLogger(__name__)

def load_docx(docx_path):
    """
    Загружает и обрабатывает DOCX документ
    Args:
        docx_path (str): Путь к DOCX файлу
    Returns:
        list: Список объектов Document, содержащих текст документа и метаданные
    """
    try:
        logger.info(f"Начало загрузки DOCX: {docx_path}")
        
        # Проверка существования файла
        if not os.path.exists(docx_path):
            error_msg = f"DOCX файл не найден по пути: {docx_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        # Получение абсолютного пути
        abs_path = os.path.abspath(docx_path)
        logger.info(f"Абсолютный путь к файлу: {abs_path}")
        
        # Проверка расширения файла
        _, ext = os.path.splitext(abs_path)
        if ext.lower() != '.docx':
            error_msg = f"Файл должен быть в формате DOCX, получен формат: {ext}"
            logger.error(error_msg)
            return None
        
        # Проверка размера файла
        file_size = os.path.getsize(abs_path) / (1024 * 1024)  # в МБ
        logger.info(f"Размер файла: {file_size:.2f} МБ")
        
        # Загружаем DOCX
        logger.info(f"Загрузка DOCX с помощью Docx2txtLoader")
        loader = Docx2txtLoader(abs_path)
        documents = loader.load()
        
        if not documents:
            logger.error("Docx2txtLoader вернул пустой список документов")
            return None
            
        logger.info(f"DOCX успешно загружен. Количество документов: {len(documents)}")
        
        # Проверка содержимого
        if documents and hasattr(documents[0], 'page_content'):
            content_sample = documents[0].page_content[:100].replace('\n', ' ')
            logger.info(f"Пример содержимого: '{content_sample}...'")
        
        return documents
    
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при загрузке DOCX: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None

if __name__ == "__main__":
    # Используйте относительный путь от текущего каталога
    current_dir = os.path.dirname(os.path.abspath(__file__))
    docx_path = os.path.join(current_dir, "..", "sources", "example.docx")
    
    documents = load_docx(docx_path)
    if documents:
        print(f"Успешно загружено {len(documents)} документов")
        print("\nПример содержимого:")
        print("=" * 50)
        print(documents[0].page_content[:1000])
        print("=" * 50) 