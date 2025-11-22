# blog/forms.py
from django import forms
from .models import Comment

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['name', 'body']
        # 给表单添加 Bootstrap 样式类
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '请输入你的昵称'}),
            'body': forms.Textarea(attrs={'class': 'form-control', 'placeholder': '请输入评论内容...', 'rows': 4}),
        }