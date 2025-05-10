import os
import logging
from .pdf_loader import load_pdf
from .docx_loader import load_docx
from .doc_loader import load_doc
from .txt_loader import load_txt
from .rtf_loader import load_rtf

# Настройка логирования
logger = logging.getLogger(__name__)

def load_document(file_path):
    """
    Универсальная функция для загрузки документа. Определяет формат по расширению файла
    и выбирает соответствующий загрузчик.
    
    Args:
        file_path (str): Путь к файлу документа
    
    Returns:
        list: Список объектов Document, содержащих текст документа и метаданные,
              или None в случае ошибки
    """
    if not os.path.exists(file_path):
        logger.error(f"Файл не найден: {file_path}")
        return None
    
    # Определяем расширение файла
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    
    logger.info(f"Определен формат файла: {ext}")
    
    # Выбираем соответствующий загрузчик
    if ext == '.pdf':
        return load_pdf(file_path)
    elif ext == '.docx':
        return load_docx(file_path)
    elif ext == '.doc':
        return load_doc(file_path)
    elif ext == '.txt':
        return load_txt(file_path)
    elif ext == '.rtf':
        return load_rtf(file_path)
    else:
        logger.error(f"Неподдерживаемый формат файла: {ext}")
        return None

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Использование: python document_loader.py <путь_к_файлу>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    documents = load_document(file_path)
    
    if documents:
        print(f"Успешно загружено {len(documents)} документов/страниц")
        print("\nПример содержимого:")
        print("=" * 50)
        print(documents[0].page_content[:1000])
        print("=" * 50)
    else:
        print("Ошибка при загрузке документа") 