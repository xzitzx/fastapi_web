"""
URL configuration for django_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

# mysite/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from blog import views as blog_views
urlpatterns = [
    path('admin/', admin.site.urls),
    # 1. 添加 Django 内置的认证路由 (包含 login 和 logout)
    path('accounts/', include('django.contrib.auth.urls')),
    # 2. 添加自定义的注册路由
    path('register/', blog_views.register, name='register'),

    path('', include('blog.urls')),
]

# 仅在开发模式下生效
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)