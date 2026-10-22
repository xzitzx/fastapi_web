# 博客

基于 FastAPI 的个人博客：访客浏览文章、发表评论；管理员登录后在网页上写作和管理。

## 环境要求

Python 3.11 或更高版本。本机使用 Homebrew 的 `python3.12`（macOS 自带的 Python 3.9 无法运行）。

## 安装

在项目根目录执行：

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

开发和运行测试还需安装 `requirements-dev.txt`（已包含 `requirements.txt`）：

```sh
.venv/bin/pip install -r requirements-dev.txt
```

## 生成密码哈希

```sh
.venv/bin/python -m app.passwords
```

按提示输入两次密码，输出一行 `scrypt$16384$8$1$...` 形式的字符串，作为 `ADMIN_PASSWORD_HASH` 的值。

## 环境变量

应用启动时从进程环境变量读取配置（不读取 `.env` 文件）。必填变量缺失或为空时无法启动，报错信息会列出缺少的变量名。

| 变量 | 必填 | 含义 | 默认值 |
| --- | --- | --- | --- |
| `SECRET_KEY` | 是 | 会话 cookie 的签名密钥 | 无 |
| `ADMIN_USERNAME` | 是 | 管理员用户名 | 无 |
| `ADMIN_PASSWORD_HASH` | 是 | 上一步生成的密码哈希 | 无 |
| `DATABASE_URL` | 否 | SQLite 数据库地址，如 `sqlite:////绝对路径/blog.db` | `sqlite:///<项目根目录>/blog.db` |
| `MEDIA_ROOT` | 否 | 上传图片（封面和正文插图）的保存目录 | `<项目根目录>/media` |

`SECRET_KEY` 用随机长字符串，可以这样生成：

```sh
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

设置示例（密码哈希含 `$`，必须用单引号）：

```sh
export SECRET_KEY='<上面生成的随机字符串>'
export ADMIN_USERNAME='<管理员用户名>'
export ADMIN_PASSWORD_HASH='<python -m app.passwords 的输出>'
```

## 启动

```sh
.venv/bin/uvicorn app.main:app --reload
```

默认地址 http://127.0.0.1:8000 ，首次启动时自动建表。`--reload` 只用于开发。

- 登录：`/login`
- 写文章：`/write`（未登录时跳转到登录页）

## 运行测试

```sh
.venv/bin/pytest -q -W error
```

测试自行设置临时的环境变量、数据库和图片目录，不需要上面的配置。

## 上线注意事项

- 会话 cookie 当前未开启 `https_only`。在 HTTPS 下部署时，应在 `app/main.py` 的 `SessionMiddleware` 参数中加上 `https_only=True`，让 cookie 只通过 HTTPS 发送。
- 应用不限制请求体大小，也不限制登录频率。应在反向代理上限制请求体大小（图片上限为 10MB）和 `/login` 的请求频率。
- 管理员使用强密码。
- `SECRET_KEY` 使用随机长字符串，不要提交到仓库；更换后已登录的会话全部失效。
- 会话保存在签名 cookie 里，退出只会清掉当前浏览器的 cookie，已泄露的旧 cookie 在过期前（14 天）仍然有效。怀疑泄露时更换 `SECRET_KEY`。
- 应用不发送 `X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy` 等安全响应头，应由反向代理添加。
