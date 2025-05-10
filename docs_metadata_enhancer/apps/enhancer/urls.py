from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'enhancer'
urlpatterns = [
    path('', views.file_system, name='file_system'),
    path('folder/<int:folder_id>/', views.file_system, name='folder_detail'),
    path('document/<int:document_id>/', views.document_detail, name='document_detail'),
    path('document/<int:document_id>/download/', views.document_download, name='document_download'),
    path('document/<int:document_id>/delete/', views.document_delete, name='document_delete'),
    path('document/<int:document_id>/rename/', views.document_rename, name='document_rename'),
    path('document/<int:document_id>/export/', views.document_export, name='document_export'),

    path('create-folder/', views.create_folder, name='create_folder'),
    path('delete-folder/', views.delete_folder, name='delete_folder'),
    path('rename-folder/', views.rename_folder, name='rename_folder'),
    path('upload-file/', views.upload_file, name='upload_file'),
    path('process/', views.index, name='process'),
    
    
    # API для работы с Wikidata
    path('api/wikidata/search/', views.wikidata_search, name='wikidata_search'),
    # Дополнительный путь для JavaScript
    path('enhancer/api/wikidata/search/', views.wikidata_search, name='wikidata_search_js'),
    
    path('api/wikidata/entity/<str:qid>/', views.wikidata_entity_info, name='wikidata_entity_info'),
    # Дополнительный путь для JavaScript
    path('enhancer/wikidata/entity/<str:qid>/info/', views.wikidata_entity_info, name='wikidata_entity_info_js'),
    
    path('api/document/<int:document_id>/wikidata/update/', views.update_document_wikidata, name='update_document_wikidata'),
    # Дополнительный путь для JavaScript
    path('enhancer/api/document/<int:document_id>/wikidata/update/', views.update_document_wikidata, name='update_document_wikidata_js'),
    
    path('api/document/<int:document_id>/wikidata/link/', views.link_entity_to_document, name='link_entity_to_document'),
    # Дополнительный путь для JavaScript
    path('enhancer/api/document/<int:document_id>/wikidata/link/', views.link_entity_to_document, name='link_entity_to_document_js'),
    
    path('api/document/<int:document_id>/wikidata/unlink/', views.unlink_entity_from_document, name='unlink_entity_from_document'),
    # Дополнительный путь для JavaScript
    path('enhancer/api/document/<int:document_id>/wikidata/unlink/', views.unlink_entity_from_document, name='unlink_entity_from_document_js'),
    
    # Обновление описаний сущностей
    path('api/document/<int:document_id>/wikidata/refresh_descriptions/', views.refresh_entity_descriptions, name='refresh_entity_descriptions'),
    # Дополнительный путь для JavaScript
    path('enhancer/api/document/<int:document_id>/wikidata/refresh_descriptions/', views.refresh_entity_descriptions, name='refresh_entity_descriptions_js'),
    
    # Обновление связей Wikidata
    path('api/document/<int:document_id>/wikidata/update/', views.update_document_wikidata, name='update_document_wikidata'),
    # Дополнительный путь для JavaScript
    path('enhancer/api/document/<int:document_id>/wikidata/update/', views.update_document_wikidata, name='update_document_wikidata_js'),
]
