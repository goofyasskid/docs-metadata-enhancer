from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User
from .forms import UserCreationForm, ProfileForm

# Register your models here.


class CustomUserAdmin(UserAdmin):
    add_form = UserCreationForm
    form = ProfileForm
    model = User
    list_display = ('email', 'first_name','last_name','phone_number', 'is_staff', 'is_active', 'is_manager', 'approved',)
    list_filter = ('email', 'is_staff', 'is_active', 'is_manager')
    fieldsets = (
        (None, {'fields': ('email', 'first_name','last_name','phone_number','image','password', )}),
        ('Permissions', {'fields': ('is_staff', 'is_active','is_superuser', 'approved', 'is_manager')}),
        ('Information', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active')}
         ),
    )
    search_fields = ('email',)
    ordering = ('email',)


admin.site.register(User, CustomUserAdmin)
