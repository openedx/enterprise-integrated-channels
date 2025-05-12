"""
Mock enterprise template tags.
"""
from django import template

register = template.Library()

@register.simple_tag
def enterprise_customer_logo_url(enterprise_customer):
    """
    Mock implementation that returns an empty string.
    """
    return ""

@register.simple_tag
def enterprise_customer_name(enterprise_customer):
    """
    Mock implementation that returns an empty string.
    """
    return ""

@register.filter
def enterprise_contains_logo(enterprise_customer):
    """
    Mock implementation that returns False.
    """
    return False

@register.inclusion_tag('enterprise/templatetags/enterprise_customer_for_request.html', takes_context=True)
def enterprise_customer_for_request(context, request=None):
    """
    Mock implementation that returns an empty dict.
    """
    return {}