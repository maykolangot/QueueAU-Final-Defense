from django import template

register = template.Library()

@register.simple_tag
def query_transform(request, **kwargs):
    query = request.GET.copy()

    # Always drop 'page' before adding new one
    query.pop('page', None)

    for k, v in kwargs.items():
        if v is None:
            query.pop(k, None)
        else:
            query[k] = v

    return query.urlencode()
