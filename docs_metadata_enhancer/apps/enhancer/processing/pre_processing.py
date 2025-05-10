import logging
import os
import re
import traceback
from typing import List

import nltk
from nltk.corpus import stopwords

from langchain.text_splitter import CharacterTextSplitter, TextSplitter
from apps.enhancer.loaders.document_loader import load_document

# Настройка логирования
logger = logging.getLogger(__name__)

# Инициализация NLTK один раз при запуске
def init_nltk():
    """
    Инициализирует NLTK, загружая необходимые данные.
    """
    try:
        # Указываем путь для NLTK-данных (локально и для сервера)
        nltk_data_path = os.getenv("NLTK_DATA", "./nltk_data")
        os.makedirs(nltk_data_path, exist_ok=True)
        nltk.data.path.append(nltk_data_path)
        
        # Проверяем наличие данных
        required_datasets = ['stopwords']
        for dataset in required_datasets:
            try:
                resource_path ='corpora/{dataset}'
                nltk.data.find(nltk_data_path)
                logger.info(f"NLTK dataset '{dataset}' already exists")
            except LookupError:
                logger.info(f"Downloading NLTK dataset '{dataset}' to {nltk_data_path}")
                nltk.download(dataset, download_dir=nltk_data_path, quiet=True)
    except Exception as e:
        logging.error(f"Ошибка инициализации NLTK: {e}")
        raise
    
    
def clean_text(text: str) -> str:
    """
    Очищает текст от лишних символов, удаляет множественные пробелы
    Args:
        text (str): Исходный текст
    Returns:
        str: Очищенный текст
    """
    try:
        logger.info(f"Начало очистки текста длиной {len(text)} символов")
        
        # Заменяем множественные переносы строк на одинарные
        cleaned_text = re.sub(r'\n+', '\n', text)
        
        # Заменяем множественные пробелы на одинарные
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
        
        # Удаляем пробелы в начале и конце строки
        cleaned_text = cleaned_text.strip()
        
        logger.info(f"Очистка текста завершена. Новая длина: {len(cleaned_text)} символов")
        return cleaned_text
    except Exception as e:
        logger.error(f"Ошибка при очистке текста: {str(e)}")
        logger.error(traceback.format_exc())
        return text  # Возвращаем исходный текст в случае ошибки


def split_text(text, chunk_size=4000, chunk_overlap=200):
    """
    Split text into chunks for processing
    Args:
        text (str): Text to split
        chunk_size (int): Size of each chunk
        chunk_overlap (int): Overlap between chunks
    Returns:
        list: List of text chunks
    """
    try:
        text_splitter= CharacterTextSplitter(
            separator=" ", 
            chunk_size=chunk_size, 
            chunk_overlap=chunk_overlap, 
        )
        chunks= text_splitter.split_text(text)
        print(f"Created {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            print(f"Chunk {i+1} length: {len(chunk)} characters")
        return chunks
    
    except Exception as e:
        print(f"Error splitting text: {e}")
        # Ручное разбиение как запасной вариант
        raise

        
def remove_stopwords(text):
    """
    Remove stopwords from text to reduce token count
    Args:
        text (str): Input text
    Returns:
        str: Text with stopwords removed
    """
    init_nltk()
    stop_words_ru = set(stopwords.words('russian'))
    stop_words_en = set(stopwords.words('english'))
    stop_words = stop_words_ru.union(stop_words_en)
    # Разбиваем текст на слова
    words = text.split()
    # Удаляем стоп-слова, сохраняя структуру
    filtered_words = [word for word in words if word.lower() not in stop_words]
    return ' '.join(filtered_words)


def load_and_combine_pdf(pdf_path):
    """
    Загружает PDF и объединяет текст всех страниц.
    Args:
        pdf_path (str): Путь к PDF-файлу
    Returns:
        str: Объединённый текст страниц или None в случае ошибки
    """
    try:
        pages = load_document(pdf_path)
        if not pages:
            logging.error("Ошибка: не удалось загрузить страницы PDF")
            return None
        return " ".join([page.page_content for page in pages])
    except Exception as e:
        logging.error(f"Ошибка при загрузке PDF: {e}")
        return None

def preprocess_text(full_text):
    """
    Очищает текст и удаляет стоп-слова.
    Args:
        full_text (str): Исходный текст
    Returns:
        str: Предобработанный текст или None в случае ошибки
    """
    try:
        if not full_text:
            logging.error("Ошибка: входной текст пуст")
            return None
        cleaned_text = clean_text(full_text)
        final_text = remove_stopwords(cleaned_text)
        return final_text
    except Exception as e:
        logging.error(f"Ошибка при предобработке текста: {e}")
        return None