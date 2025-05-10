import os
import logging
import traceback
from langchain_community.document_loaders import TextLoader

# Настройка логирования
logger = logging.getLogger(__name__)

def load_txt(txt_path):
    """
    Загружает и обрабатывает текстовый файл
    Args:
        txt_path (str): Путь к TXT файлу
    Returns:
        list: Список объектов Document, содержащих текст документа и метаданные
    """
    try:
        logger.info(f"Начало загрузки TXT: {txt_path}")
        
        # Проверка существования файла
        if not os.path.exists(txt_path):
            error_msg = f"TXT файл не найден по пути: {txt_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        # Получение абсолютного пути
        abs_path = os.path.abspath(txt_path)
        logger.info(f"Абсолютный путь к файлу: {abs_path}")
        
        # Проверка расширения файла
        _, ext = os.path.splitext(abs_path)
        if ext.lower() != '.txt':
            error_msg = f"Файл должен быть в формате TXT, получен формат: {ext}"
            logger.error(error_msg)
            return None
        
        # Проверка размера файла
        file_size = os.path.getsize(abs_path) / (1024 * 1024)  # в МБ
        logger.info(f"Размер файла: {file_size:.2f} МБ")
        
        # Определение кодировки файла
        encodings = ['utf-8', 'windows-1251', 'cp1251', 'latin-1', 'ascii']
        encoding_to_use = None
        
        for encoding in encodings:
            try:
                with open(abs_path, 'r', encoding=encoding) as f:
                    f.read(100)  # Пробуем прочитать первые 100 символов
                encoding_to_use = encoding
                logger.info(f"Определена кодировка файла: {encoding}")
                break
            except UnicodeDecodeError:
                continue
        
        if not encoding_to_use:
            logger.error("Не удалось определить кодировку файла")
            return None
        
        # Загружаем TXT
        logger.info(f"Загрузка TXT с помощью TextLoader с кодировкой {encoding_to_use}")
        loader = TextLoader(abs_path, encoding=encoding_to_use)
        documents = loader.load()
        
        if not documents:
            logger.error("TextLoader вернул пустой список документов")
            return None
            
        logger.info(f"TXT успешно загружен. Количество документов: {len(documents)}")
        
        # Проверка содержимого
        if documents and hasattr(documents[0], 'page_content'):
            content_sample = documents[0].page_content[:100].replace('\n', ' ')
            logger.info(f"Пример содержимого: '{content_sample}...'")
        
        return documents
    
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при загрузке TXT: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None

if __name__ == "__main__":
    # Используйте относительный путь от текущего каталога
    current_dir = os.path.dirname(os.path.abspath(__file__))
    txt_path = os.path.join(current_dir, "..", "sources", "example.txt")
    
    documents = load_txt(txt_path)
    if documents:
        print(f"Успешно загружено {len(documents)} документов")
        print("\nПример содержимого:")
        print("=" * 50)
        print(documents[0].page_content[:1000])
        print("=" * 50) 