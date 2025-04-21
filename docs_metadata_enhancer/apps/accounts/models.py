from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from PIL import Image
from django.urls import reverse
from phonenumber_field.modelfields import PhoneNumberField
# Create your models here.


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """

    def create_user(self, email, password, **extra_fields):
        """
        Create and save a User with the given email and password.
        """
        if not email:
            raise ValueError("The Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self.db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None

    #inherited fields: username, email, first_name, last_name, password, is_staff, is_active 

    email = models.EmailField("Email address", unique=True)
    image = models.ImageField(
        "Image", default="default_account_picture.png", upload_to='account_pictures')
    phone_number = PhoneNumberField(blank=True) #https://django-phonenumber-field.readthedocs.io/
    approved =  models.BooleanField(default=False)
    is_manager =  models.BooleanField(default=False)
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = "Users"
        verbose_name_plural = "Users"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        img = Image.open(self.image.path)
        if img.height > 300 or img.width > 300:
            output_size = (300, 300)
            img.thumbnail(output_size)
            img.save(self.image.path)

    def __str__(self,):
        return f'{self.first_name} {self.last_name}, {self.email}, {self.phone_number}'

    def get_absolute_url(self):
        return reverse('accounts:profile')
