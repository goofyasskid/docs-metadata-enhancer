from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'accounts'
urlpatterns = [

    path('accounts/profile/', views.profile_details, name='profile'),
 
    path('accounts/profile/edit', views.ProfileUpdateView.as_view(), name='profile_edit'),
    path('accounts/signup/', views.SignupView.as_view(), name='signup'),
    path("accounts/login/", auth_views.LoginView.as_view(template_name='accounts/login.html'), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("activate/<uidb64>/<token>", views.activate, name='activate'),
    path(
        'accounts/reset_password/',
        views.PasswordResetView.as_view(),
        name="reset_password"),
    path(
        'accounts/reset_password_sent/',
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset/password_reset_sent.html"),
        name='password_reset_done'),
    path(
        'accounts/reset/<uidb64>/<token>/',
         views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm"),
    path(
        'accounts/reset/done',
         auth_views.PasswordResetCompleteView.as_view(
         template_name="accounts/password_reset/password_reset_done.html"),
         name="password_reset_complete"),
]
