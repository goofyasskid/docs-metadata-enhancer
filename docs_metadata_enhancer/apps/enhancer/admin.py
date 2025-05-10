from django.contrib import admin
from .models import Folder, Document, WikidataEntity, DocumentEntityRelation

@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'owner', 'created_at', 'updated_at')
    list_filter = ('owner', 'created_at')
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('name', 'file_type', 'folder', 'owner', 'created_at', 'updated_at')
    list_filter = ('file_type', 'owner', 'created_at')
    search_fields = ('name', 'content')
    ordering = ['-created_at']
    readonly_fields = ('file_type',)

@admin.register(WikidataEntity)
class WikidataEntityAdmin(admin.ModelAdmin):
    list_display = ('qid', 'label_ru', 'label_en', 'created_at')
    search_fields = ('qid', 'label_ru', 'label_en')
    list_filter = ('created_at',)

@admin.register(DocumentEntityRelation)
class DocumentEntityRelationAdmin(admin.ModelAdmin):
    list_display = ('document', 'entity', 'field_category', 'name', 'confidence', 'created_at')
    list_filter = ('field_category','created_at')
    search_fields = ('document__name', 'entity__qid', 'entity__label_ru')
