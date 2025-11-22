# blog/templatetags/blog_extras.py
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='to_markdown')
def to_markdown(value):
    # 使用 markdown 库转换文本
    # extra: 支持更多扩展语法（如表格、脚注）
    # codehilite: 代码高亮支持
    return mark_safe(markdown.markdown(value, extensions=[
        'markdown.extensions.extra',
        'markdown.extensions.codehilite',
        'markdown.extensions.toc',
    ]))