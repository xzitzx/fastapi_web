from django.db import models

# Create your models here.
# blog/models.py
# blog/models.py
from django.db import models
from django.contrib.auth.models import User

class Post(models.Model):
    title = models.CharField(max_length=200, verbose_name="标题")
    # 新增 upload_to 参数，图片会自动存入 media/posts/ 文件夹
    cover = models.ImageField(upload_to='posts/', blank=True, null=True, verbose_name="封面图")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="作者")
    body = models.TextField(verbose_name="正文")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']
        verbose_name = "文章"
        verbose_name_plural = "文章列表"
class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments', verbose_name="所属文章")
    name = models.CharField(max_length=80, verbose_name="昵称")
    body = models.TextField(verbose_name="评论内容")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="评论时间")

    class Meta:
        ordering = ['created_at'] # 按照时间顺序排列
        verbose_name = "评论"
        verbose_name_plural = "评论列表"

    def __str__(self):
        return f'{self.name} 评论了 {self.post}'

