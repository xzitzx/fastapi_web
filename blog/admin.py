from django.contrib import admin

# Register your models here.
# blog/admin.py
from django.contrib import admin
from .models import Post

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at') # 在列表页显示的字段
    search_fields = ('title', 'body') # 添加搜索功能