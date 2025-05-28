from django import template

register = template.Library()

@register.filter
def filter_shares(shares, device):
    return shares.filter(device=device)

@register.filter
def truncate_id(value):
    if len(value) > 10:
        return f"{value[:8]}..."
    return value