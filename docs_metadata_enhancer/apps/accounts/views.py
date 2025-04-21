from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (PasswordResetConfirmView,
                                       PasswordResetView)
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import CreateView, ListView, UpdateView

from .forms import ProfileForm, UserCreationForm
from .models import User
from .tokens import account_activation_token
from .utils import send_account_email_confirmation

# Create your views here.


class SignupView(CreateView):
    model = User
    form_class = UserCreationForm
    template_name = 'accounts/signup.html'
    redirect_authenticated_user = False

    @method_decorator(sensitive_post_parameters())
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        if self.redirect_authenticated_user and self.request.user.is_authenticated:
            redirect_to = self.get_success_url()
            if redirect_to == self.request.path:
                raise ValueError(
                    "Redirection loop for authenticated user detected. Check that "
                    "your LOGIN_REDIRECT_URL doesn't point to a register page."
                )
            return HttpResponseRedirect(redirect_to)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        valid = super().form_valid(form)
        user = form.save()
        user.is_active = False
        user.save()
        send_account_email_confirmation(self.request, user)
        return valid

    def get_success_url(self):
        return '/'


@login_required
def profile_details(request):
    user = request.user

    context = {
        "user": user,
    }
    return render(request, 'accounts/profile.html', context)

class ProfileView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "accounts/profile.html"

    def get_object(self):
        return get_object_or_404(User, id=self.request.user.id)
    
class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = "accounts/profile_edit.html"

    def get_object(self):
        return get_object_or_404(User, id=self.request.user.id)


class PasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset/password_reset.html"
    email_template_name = 'accounts/email_messages/password_reset_email.txt'
    success_url = reverse_lazy('accounts:password_reset_done')


class PasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset/password_reset_form.html"
    success_url = reverse_lazy('accounts:password_reset_complete')


def activate(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, 'Спасибо за подтверждение Email. Теперь вы можете войти.')
        return redirect('accounts:login')
    else:
        messages.error(request, 'Срок действия ссылки истёк')
        return redirect('accounts:login')

