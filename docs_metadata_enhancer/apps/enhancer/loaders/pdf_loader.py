import os
import logging
import traceback
from dotenv import load_dotenv, find_dotenv
from langchain_community.document_loaders import PyPDFLoader

# Настройка логирования
logger = logging.getLogger(__name__)

def load_pdf(pdf_path):
    """
    Load and process a PDF document
    Args:
        pdf_path (str): Path to the PDF file
    Returns:
        list: List of Document objects containing page content and metadata
    """
    try:
        logger.info(f"Начало загрузки PDF: {pdf_path}")
        
        # Check if file exists
        if not os.path.exists(pdf_path):
            error_msg = f"PDF file not found at path: {pdf_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
        # Get absolute path
        abs_path = os.path.abspath(pdf_path)
        logger.info(f"Абсолютный путь к файлу: {abs_path}")
        
        # Проверка расширения файла
        _, ext = os.path.splitext(abs_path)
        if ext.lower() != '.pdf':
            error_msg = f"Файл должен быть в формате PDF, получен формат: {ext}"
            logger.error(error_msg)
            return None
        
        # Проверка размера файла
        file_size = os.path.getsize(abs_path) / (1024 * 1024)  # в МБ
        logger.info(f"Размер файла: {file_size:.2f} МБ")
        
        # Загружаем PDF
        logger.info(f"Загрузка PDF с помощью PyPDFLoader")
        loader = PyPDFLoader(abs_path)
        pages = loader.load()
        
        if not pages:
            logger.error("PyPDFLoader вернул пустой список страниц")
            return None
            
        logger.info(f"PDF успешно загружен. Количество страниц: {len(pages)}")
        
        # Проверка содержимого первой страницы
        if pages and hasattr(pages[0], 'page_content'):
            content_sample = pages[0].page_content[:100].replace('\n', ' ')
            logger.info(f"Пример содержимого: '{content_sample}...'")
        
        return pages
    
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при загрузке PDF: {str(e)}")
        logger.error(f"Трассировка: {traceback.format_exc()}")
        return None

if __name__ == "__main__":
    # Use a relative path from the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # pdf_path = os.path.join(current_dir, "..", "sources", "sfbu-2024-2025-university-catalog-8-20-2024.pdf")
    pdf_path = "C://Users/zheny/Downloads/test.pdf"
    
    
    pages = load_pdf(pdf_path)
    if pages:
        print(f"Successfully loaded {len(pages)} pages")
        # Print page 8 sample with larger content slice
        print("\nPage 8 content sample:")
        print("=" * 50)
        print(pages[5].page_content[:1000])  # Using index 7 for page 8 (0-based indexing)
        print("=" * 50)