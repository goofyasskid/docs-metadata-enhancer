from django import template

register = template.Library()

@register.filter
def get_folder_path(folder):
    path = []
    current = folder
    while current is not None:
        path.insert(0, current)
        current = current.parent
    return path 