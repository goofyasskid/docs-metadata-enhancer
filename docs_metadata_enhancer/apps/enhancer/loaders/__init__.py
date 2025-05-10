"""
Модуль загрузчиков документов для приложения Enhancer
"""

from .document_loader import load_document
from .pdf_loader import load_pdf
from .docx_loader import load_docx
from .doc_loader import load_doc
from .txt_loader import load_txt
from .rtf_loader import load_rtf

__all__ = [
    'load_document',
    'load_pdf',
    'load_docx',
    'load_doc',
    'load_txt',
    'load_rtf',
] 