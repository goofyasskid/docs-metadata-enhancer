from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import User


class UserCreationForm(UserCreationForm):

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'password1', 'password2']


#https://django-phonenumber-field.readthedocs.io/
class ProfileForm(UserChangeForm):

    class Meta:
        model = User
        fields = ['image', 'email', 'first_name', 'last_name' ,'phone_number']
