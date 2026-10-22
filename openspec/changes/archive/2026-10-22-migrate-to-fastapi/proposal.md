## Why

现有站点基于 Django + Bootstrap 默认样式，视觉单调，且文案（"我的博客"、"WELCOME"）不符合站长偏好。站长希望把后端换成 FastAPI，改为简约风格，并且在前台风格统一的写作页里写文章，而不是在通用后台里写。线上没有需要保留的数据，可以从空库开始，这是一次性完成迁移的时机。

## What Changes

- 后端从 Django 改为 FastAPI，模板从 Django Template 改为 Jinja2，ORM 从 Django ORM 改为 SQLAlchemy，数据库继续用 SQLite 单文件。
- **BREAKING** 删除访客注册、登录、注销（`/register/`、`/accounts/login/`、`/accounts/logout/` 不再存在）。只保留一个管理员账号，账号和密码哈希来自环境变量。
- **BREAKING** 删除 `/admin` 后台，不引入任何通用后台。改为自建：
  - 登录页 `/login`：前台不放任何入口，站长直接访问地址；登录后导航栏出现"写文章"和"退出"。
  - 写作页：新建和编辑文章共用，标题、封面图、Markdown 正文，正文可在"编辑"和"预览"之间切换，预览效果与发布后一致。
  - 草稿：文章可以只保存为草稿，草稿只有登录后能看到；已发布的文章可以转回草稿。
  - 正文插图：点按钮上传或直接粘贴图片，上传后自动在光标处插入 Markdown 图片语法。
  - 登录后在文章详情页可以编辑、删除文章，删除任意评论。
- **BREAKING** 文章去掉"作者"字段（单人站点，不再关联用户表）；新增"状态"（草稿或已发布）和"发布时间"。前台显示和排序使用发布时间。
- **BREAKING** 不迁移旧数据，新库从空开始；移除 `mysqlclient` 依赖。
- 前台改为简约风格，以预览稿为准：白底单栏、系统字体、单一强调色、细线分隔，去掉 Bootstrap 和全站背景大图。
  - 首页：第一屏为全屏背景视频，除导航外不叠加任何文字；下方为最近文章列表。
  - 文章列表：标题、摘要、日期、阅读时长、评论数，每页 5 篇。
  - 文章详情：Markdown 渲染、代码高亮（补上旧版缺失的 Pygments 样式表）、上一篇/下一篇、评论区。
  - 访客看到的导航只有"首页"、"文章"；页脚只有"© 年份"；全站不出现"我的博客"、"WELCOME"、"Powered by"之类字样。
- 修复旧版问题：时间按北京时间显示（旧版显示 UTC）；密钥不再硬编码在代码里；`requirements.txt` 改为 UTF-8 编码。
- 所有提交表单的操作（评论、登录、退出、写作、删除、上传）都有 CSRF 防护；访客评论仍然只需填昵称和内容。
- 迁移完成后删除 Django 代码，以及新设计不再使用的 `item1.jpg`、`item2.jpg`（两张图仍保留在 git 历史中）。

## Capabilities

### New Capabilities

- `blog-pages`: 前台页面，包括首页、文章列表与分页、文章详情（Markdown、代码高亮、阅读时长、上一篇/下一篇）、404 页、页面框架（导航、页脚、文案约束）、北京时间显示，以及登录后才出现的导航项、草稿区和管理按钮。
- `comments`: 访客评论，包括提交、字段校验、CSRF 防护、提交后重定向、内容转义、展示，以及登录后删除评论。
- `admin-auth`: 站长身份，包括基于环境变量的单管理员配置、生成密码哈希的命令、登录与退出、受保护操作的访问控制、缺少必要配置时拒绝启动。
- `authoring`: 写作，包括新建与编辑文章、编辑/预览切换、草稿与发布、封面图、正文插图上传、删除文章。

### Modified Capabilities

（无。项目此前没有 OpenSpec 规格。）

## Non-Goals

- 不做暗色模式、标签/分类、搜索、RSS、站内目录。
- 不做浏览器本地自动保存、定时自动保存草稿、版本历史。
- 不做所见即所得编辑器，不引入任何前端 Markdown 编辑器库；写作页就是一个文本框加服务端渲染的预览。
- 不清理未被引用的正文插图文件（删除文章时只删除它的封面图）。
- 不迁移旧数据，不提供 Django 数据导入脚本。
- 不保留访客注册和登录，不做多管理员、权限分级、找回密码。
- 不提供对外 JSON API；FastAPI 默认的 `/docs`、`/redoc`、`/openapi.json` 一并关闭。
- 不做部署相关配置（Docker、Nginx、systemd、HTTPS 证书）。
- 不引入 CSS 框架、前端框架或前端构建工具，不加载外部字体或 CDN 资源。
- 不做评论审核流程、垃圾评论过滤、登录或评论的频率限制。
- 不重命名 GitHub 仓库 `django_web`。
- 不引入数据库迁移工具；本次只用建表，待首次需要改表结构时再引入 Alembic。

## Impact

- 代码：删除 `manage.py`、`django_web/`、`blog/` 下全部 Django 代码；新增 `app/`（FastAPI 应用、模板、样式、少量原生 JS）和 `tests/`。
- 依赖：`requirements.txt` 全部替换。新依赖为 fastapi、uvicorn、jinja2、python-multipart、itsdangerous、sqlalchemy、pillow、markdown、pygments；测试依赖为 pytest、httpx2。确切版本在实现时从 PyPI 核实后锁定。
- 运行环境：Python 最低 3.11（Starlette 1.9.0、Markdown 3.11.2、Pillow 13.0.0 的要求），本机使用 Homebrew 的 Python 3.12。系统自带的 Python 3.9.6 无法运行。
- 配置：新增必填环境变量 `SECRET_KEY`、`ADMIN_USERNAME`、`ADMIN_PASSWORD_HASH`；提供生成密码哈希的命令。
- URL：保留 `/`、`/blog/`、`/post/<id>/`；新增 `/login`、`/logout`、`/write`、`/post/<id>/edit`、`/post/<id>/delete`、`/comments/<id>/delete`、`/preview`、`/uploads`；删除 `/admin` 和注册、登录、注销的旧路由。
- 数据：新 SQLite 文件和上传目录 `media/` 从空开始，均被 `.gitignore` 忽略。
