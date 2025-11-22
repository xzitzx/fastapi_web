from django.shortcuts import render

# Create your views here.
# blog/views.py
from django.shortcuts import render, get_object_or_404
from .models import Post

# 首页：文章列表
# blog/views.py
from django.shortcuts import render, get_object_or_404,redirect
from django.core.paginator import Paginator  # 1. 引入分页器
from .models import Post
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .forms import CommentForm
def post_list(request):
    # 获取所有文章
    post_list = Post.objects.all()

    # 2. 实例化分页器，每页显示 5 篇文章
    paginator = Paginator(post_list, 5)

    # 3. 获取 URL 中的页码参数 (例如: /?page=2)
    page_number = request.GET.get('page')

    # 4. 获取当前页的数据对象
    page_obj = paginator.get_page(page_number)

    # 5. 传递 page_obj 给模板，而不是原来的 post_list
    return render(request, 'blog/post_list.html', {'page_obj': page_obj})


# 修改 post_detail 处理评论
def post_detail(request, pk):
    post = get_object_or_404(Post, pk=pk)

    # 处理评论提交
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post  # 关联当前文章
            comment.save()
            return redirect('blog:post_detail', pk=post.pk)  # 刷新页面
    else:
        form = CommentForm()

    return render(request, 'blog/post_detail.html', {
        'post': post,
        'form': form,  # 传递表单到模板
    })


# 新增：用户注册视图
def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # 注册成功后直接登录
            return redirect('blog:post_list')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def landing(request):
    return render(request, 'blog/landing.html')