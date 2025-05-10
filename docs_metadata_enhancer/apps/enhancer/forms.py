# apps/enhancer/forms.py
from django import forms
from django.forms import formset_factory
import json

# Форма для одного элемента массива (например, {"name": ..., "wikidata": ...})
class ArrayItemForm(forms.Form):
    name = forms.CharField(
        label="Название",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Название'})
    )
    wikidata = forms.CharField(
        label="Wikidata ID",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Wikidata ID'})
    )

# Основная форма для метаданных
class MetadataForm(forms.Form):
    def __init__(self, metadata=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.formsets = {}
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, list):
                    # Для массивов создаём formset
                    initial_data = [
                        {'name': item['name'], 'wikidata': item['wikidata'] if item.get('wikidata') else ""}
                        for item in value if isinstance(item, dict)
                    ]
                    self.formsets[key] = formset_factory(ArrayItemForm, extra=0)(initial=initial_data, prefix=key)
                elif isinstance(value, dict):
                    # Для вложенных словарей (например, title)
                    for subkey, subvalue in value.items():
                        field_name = f"{key}_{subkey}"
                        self.fields[field_name] = forms.CharField(
                            label=f"{key.capitalize()} {subkey.capitalize()}",
                            initial=subvalue if subvalue is not None else "",
                            required=False,
                            widget=forms.TextInput(attrs={'class': 'form-control', 'data-dict': key, 'data-subkey': subkey})
                        )
                else:
                    # Для простых значений (например, summary)
                    self.fields[key] = forms.CharField(
                        label=key.capitalize(),
                        initial=value,
                        required=False,
                        widget=forms.TextInput(attrs={'class': 'form-control'})
                    )