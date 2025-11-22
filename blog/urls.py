# blog/urls.py
from django.urls import path
from . import views

app_name = 'blog' # 命名空间

urlpatterns = [
    # 1. 根路径：显示欢迎页 (landing)
    path('', views.landing, name='landing'),

    # 2. /blog/ 路径：显示文章列表 (原来的首页)
    # 注意：name='post_list' 保持不变，这样原来的跳转逻辑大多不需要改
    path('blog/', views.post_list, name='post_list'),

    # ... 其他路由保持不变 ...
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
]