from django import template
from apps.accounts.models import User


register = template.Library()


@register.filter
def get_tag(tags):
    return 'danger' if tags == 'error' else tags


@register.filter
def get_sender(q):
	return q.first().sender


@register.filter
def get_user(id):
	return User.objects.get(id=id)


@register.filter
def get_first_name(id):
	return User.objects.get(id=id).first_name


@register.filter
def get_last_name(id):
	return User.objects.get(id=id).last_name

@register.filter
def get_id(id):
	return User.objects.get(id=id).id

@register.filter
def get_image(id):
	return User.objects.get(id=id).image.url



@register.filter
def length(text):
	if len(text)>30:
		return True
	else:
		return False

