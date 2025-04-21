from django.utils.http import urlsafe_base64_encode
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.contrib.sites.shortcuts import get_current_site
from .tokens import account_activation_token
from django.template.loader import render_to_string


def send_account_email_confirmation(request, user):
    current_site = get_current_site(request)
    subject = 'Confirm your email'
    message = render_to_string('accounts/email_messages/email_confirmation.txt', {
        'user': user,
        'domain': current_site.domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': account_activation_token.make_token(user),
    })
    user.email_user(subject, message)


# def send_account_password_reset_request(request, user):
#     current_site = get_current_site(request)
#     subject = 'Reset password request'
#     message = render_to_string('accounts/email_messages/password_reset_email.txt', {
#         'user': user,
#         'domain': current_site.domain,
#         'uid': urlsafe_base64_encode(force_bytes(user.pk)),
#         'token': account_activation_token.make_token(user),
#     })
#     user.email_user(subject, message)
