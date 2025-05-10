from django.db import models
from apps.accounts.models import User

# Create your models here.

class Folder(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название папки")
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, 
                             related_name='children', verbose_name="Родительская папка")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Владелец")

    class Meta:
        verbose_name = "Папка"
        verbose_name_plural = "Папки"
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def is_root(self):
        return self.parent is None

    def get_path(self):
        if self.is_root:
            return self.name
        return f"{self.parent.get_path()}/{self.name}"


class WikidataEntity(models.Model):
    """Модель для хранения сущностей Wikidata"""
    qid = models.CharField(max_length=20, unique=True, verbose_name="Идентификатор Q")
    label_ru = models.CharField(max_length=255, blank=True, null=True, verbose_name="Метка на русском")
    label_en = models.CharField(max_length=255, blank=True, null=True, verbose_name="Метка на английском")
    description_ru = models.TextField(blank=True, null=True, verbose_name="Описание на русском")
    description_en = models.TextField(blank=True, null=True, verbose_name="Описание на английском")
    properties = models.JSONField(default=dict, blank=True, verbose_name="Свойства и значения")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Сущность Wikidata"
        verbose_name_plural = "Сущности Wikidata"
        ordering = ['qid']

    def __str__(self):
        if self.label_ru:
            return f"{self.qid} - {self.label_ru}"
        elif self.label_en:
            return f"{self.qid} - {self.label_en}"
        return self.qid
    
    def to_dict(self):
        """Преобразование модели в словарь для использования в метаданных"""
        return {
            'id': self.qid,
            'label_ru': self.label_ru or '',
            'label_en': self.label_en or '',
            'description_ru': self.description_ru or '',
            'description_en': self.description_en or '',
            'properties': self.properties
        }


class Document(models.Model):
    DOCUMENT_TYPES = [
        ('pdf', 'PDF'),
        ('txt', 'Text'),
        ('doc', 'Word'),
        ('docx', 'Word (new)'),
        ('rtf', 'Rich Text'),
    ]

    PROCESSING_STATUS = [
        ('pending', 'Ожидание'),
        ('processing', 'Обработка'),
        ('success', 'Успешно'),
        ('failed', 'Не удалось'),
    ]
    
    name = models.CharField(max_length=255, verbose_name="Название документа")
    file = models.FileField(upload_to='docs/', verbose_name="Файл")
    file_type = models.CharField(max_length=10, choices=DOCUMENT_TYPES, verbose_name="Тип файла")
    folder = models.ForeignKey(Folder, on_delete=models.CASCADE, null=True, blank=True, related_name='documents', 
                             verbose_name="Папка")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Владелец")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    content = models.TextField(blank=True, null=True, verbose_name="Содержимое документа")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Метаданные")
    meta_wikidata = models.JSONField(default=dict, blank=True, verbose_name="Связи метаданных с Wikidata")
    processing_status = models.CharField(max_length=20, choices=PROCESSING_STATUS, default='pending', verbose_name="Статус обработки")
    task_id = models.CharField(max_length=50, blank=True, null=True, verbose_name="ID задачи Celery")
    processing_errors = models.TextField(blank=True, null=True, verbose_name="Ошибки обработки")

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Автоматически определяем тип файла при сохранении
        if not self.file_type:
            extension = self.file.name.split('.')[-1].lower()
            for type_code, _ in self.DOCUMENT_TYPES:
                if extension == type_code:
                    self.file_type = type_code
                    break
        super().save(*args, **kwargs)
    
    def get_task_status(self):
        """Получает текущий статус задачи Celery, связанной с документом."""
        if not self.task_id:
            return None
        
        from celery.result import AsyncResult
        result = AsyncResult(self.task_id)
        return result.status


class DocumentEntityRelation(models.Model):
    """Модель для связи документа с сущностью Wikidata и указания поля"""
    FIELD_CATEGORIES = [
        ('creator', 'Creator'),
        ('organizations', 'Organizations'),
        ('title', 'Title'),
        ('keywords', 'Keywords'),
        ('subject', 'Subject'),
        ('document_language', 'Document Language'),
        ('contributor', 'Contributor'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='entity_relations', 
                               verbose_name="Документ")
    entity = models.ForeignKey(WikidataEntity, on_delete=models.CASCADE, related_name='document_relations',
                             verbose_name="Сущность Wikidata")
    field_category = models.CharField(max_length=50, choices=FIELD_CATEGORIES, verbose_name="Категория поля", null=True, blank=True)
    name = models.CharField(max_length=255, verbose_name="Имя сущности", null=True, blank=True)
    field_key = models.CharField(max_length=255, verbose_name="Ключ поля метаданных", null=True, blank=True)
    field_value = models.CharField(max_length=255, verbose_name="Значение поля метаданных", null=True, blank=True)
    confidence = models.FloatField(default=1.0, verbose_name="Уверенность связи")
    context = models.TextField(blank=True, null=True, verbose_name="Контекст упоминания")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Связь документа с сущностью"
        verbose_name_plural = "Связи документов с сущностями"
        unique_together = ('document', 'entity', 'field_category', 'field_key', 'field_value')
        ordering = ['-confidence']

    def __str__(self):
        field_info = f"{self.field_key}: {self.field_value}" if self.field_key and self.field_value else self.field_category
        return f"{self.document.name} - {self.entity} ({field_info})"
