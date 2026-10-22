## Context

现有项目是单应用 Django 5.2 站点（`blog` 应用：Post、Comment 两个模型，6 个模板），依赖 Django admin 写文章、Django auth 做注册登录、Django CSRF 中间件保护表单。迁移动机见 proposal.md 的 Why，行为要求见 `specs/`。

已核实的约束（2026-10-22 查询 PyPI）：

- fastapi 0.159.1（Python ≥3.10）、starlette 1.9.0（Python ≥3.11）、SQLAlchemy 2.1.6、Jinja2 3.1.6、Markdown 3.11.2（Python ≥3.11）、Pygments 2.21.0、Pillow 13.0.0（Python ≥3.11）、uvicorn 0.54.0、python-multipart 0.0.32、itsdangerous 2.2.0、pytest 9.1.1、httpx2 2.16.0（Python ≥3.11）。
- 本机 `python3` 为 3.9.6，不满足要求；`/opt/homebrew/bin/python3.12` 可用。

## Goals / Non-Goals

**Goals:**
- 用最少的依赖和代码复刻旧站的公开功能，新增自建的登录与写作功能，满足 `specs/` 的全部场景。
- 安全措施不低于旧版：CSRF、输出转义、鉴权、密码哈希；新增上传文件的内容校验。

**Non-Goals:**
- 不做异步数据库访问；站点流量小，同步 SQLAlchemy 足够。
- 不抽象出 service/repository 层；路由函数直接查询。
- 不做多环境配置体系，只读环境变量。

## Decisions

### 1. 目录结构

```
app/
  main.py        创建应用、挂载 /static 和 /media、注册路由与 404 处理
  config.py      读取并校验环境变量
  db.py          engine、Session、Base、建表
  models.py      Post、Comment
  passwords.py   密码哈希与校验，不依赖其他 app 模块；`python -m app.passwords` 生成哈希
  security.py    CSRF、登录状态判断、凭据校验、受保护操作的检查
  templating.py  Jinja2 环境、过滤器、注入 is_admin / csrf_token / 年份的渲染函数
  rendering.py   Markdown 渲染、摘要、阅读时长、北京时间格式化
  images.py      图片校验、去元数据、保存、删除
  routes/
    pages.py     首页、列表、详情、提交评论
    auth.py      登录、退出
    authoring.py 写作页、保存、删除文章与评论、预览、上传
  templates/     base、home、post_list、post_detail、write、login、404、_preview（片段）
  static/        css/site.css、css/code.css、js/write.js、videos/
tests/
```

- MUST 放在现有仓库内，在 `feat/fastapi-migration` 分支完成；Django 代码在新版测试全部通过后再删除。
- 备选：新建仓库。放弃理由：旧仓库已有远端和历史，换仓库对单人项目没有收益。

### 2. 依赖与运行环境

- MUST 使用 Python ≥3.11；本地 MUST 用 `python3.12 -m venv .venv` 建虚拟环境。
- `requirements.txt` MUST 为 UTF-8 编码，MUST 用 `==` 锁定确切版本；版本 MUST 在实现时从 PyPI 核实，并用 `pip install` 实际安装通过后再写入。
- 测试依赖 MUST 放在单独的 `requirements-dev.txt`，用 `-r requirements.txt` 引用运行依赖。
- MUST NOT 引入以下清单之外的依赖：fastapi、uvicorn、jinja2、python-multipart、itsdangerous、sqlalchemy、pillow、markdown、pygments；测试用 pytest、httpx2。配置读取、密码哈希、CSRF 令牌、随机文件名、时区一律用标准库（`os`、`hashlib`、`hmac`、`secrets`、`zoneinfo`）。
- 前端 MUST NOT 引入任何 JS 库；写作页的交互用一个原生 JS 文件 `write.js` 实现。
- 备选：`fastapi[standard]`。放弃理由：会额外带入 email-validator、fastapi-cli、opentelemetry-sdk 等用不上的包（`opentelemetry-api` 是 fastapi 本身的依赖，无法避免）。
- 备选：sqladmin。用户决定改为自建写作页，已放弃。

### 3. 数据层

- MUST 使用 SQLAlchemy 2.x 同步 API 和 SQLite 单文件，默认路径 `blog.db`（项目根目录，加入 `.gitignore`），可由环境变量 `DATABASE_URL` 覆盖；上传目录默认 `media/`，可由 `MEDIA_ROOT` 覆盖。测试 MUST 使用临时数据库和临时上传目录。
- SQLite 连接 MUST 设置 `check_same_thread=False`，并在每个连接上执行 `PRAGMA foreign_keys=ON`。
- 模型：
  - `Post`：id、title（String(200)，非空）、body（Text，非空，可为空串）、cover（String(255)，可空，存相对 `MEDIA_ROOT` 的路径）、status（String(10)，取值 `draft` 或 `published`，用 CheckConstraint 约束）、created_at、updated_at、published_at（可空）。
  - `Comment`：id、post_id（外键，`ondelete="CASCADE"`）、name（String(80)）、body（Text）、created_at。
  - `Post.comments` 关系 MUST 设置 `cascade="all, delete-orphan"`。
- `published_at` 只在状态第一次变为 `published` 且该字段为空时写入，之后 MUST NOT 修改。前台排序、日期显示、上一篇/下一篇都用 `published_at`，相同时以 id 决定先后。
- 时间字段 MUST 以 UTC 存储（应用层写入 `datetime.now(timezone.utc)`），展示时 MUST 用 `zoneinfo.ZoneInfo("Asia/Shanghai")` 转换。SQLite 不保存时区信息，读取后 MUST 视为 UTC 再转换。
- 应用启动时用 `Base.metadata.create_all` 建表。
- 备选：现在就引入 Alembic。放弃理由：从空库开始且暂无改表需求；首次改表时再引入，并用 `alembic stamp` 标记现有结构为基线。

### 4. 前台页面

- MUST 使用 Jinja2 模板，MUST 开启自动转义；实现时 MUST 读安装后的 starlette `templating.py` 确认 `Jinja2Templates` 的默认 autoescape 行为，未默认开启则显式开启。
- 评论内容的换行 MUST 通过 CSS `white-space: pre-line` 保留，MUST NOT 用 `|safe` 或手工拼接 `<br>`。
- 文章正文 MUST 用 Markdown 扩展 `extra`、`codehilite`、`toc` 渲染，渲染结果标记为安全输出。正文只有站长能写，视为可信内容。详情页和 `/preview` MUST 调用同一个渲染函数。
- 代码高亮样式 MUST 由 `pygmentize -S <style> -f html -a .codehilite` 生成并提交为 `static/css/code.css`；样式名 MUST 先用 `pygmentize -L styles` 确认存在，选浅色主题。
- 摘要 MUST 取 Markdown 渲染后去除标签的纯文本。
- 列表页评论数 MUST 用一次带子查询或 `GROUP BY` 的查询取得，MUST NOT 对每篇文章单独查询。
- 分页规则见 `specs/blog-pages`，自行实现，不引入分页库。
- 404：MUST 为 `StarletteHTTPException` 注册处理器，404 时渲染 `404.html`；其他状态码交回默认处理。
- `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`。
- 模板通过一个 `is_admin` 变量决定是否渲染登录后的导航项、草稿区和管理按钮。

### 5. 视觉

- MUST 按预览稿（claude.ai artifact `6HJpc2DVCSXxczH9zNzzSa` 的"首页 B"、"文章列表"、"文章详情"、"写文章"、"登录页"）实现。
- MUST 只用一个自写样式表 `site.css`，用 CSS 变量定义颜色：背景 `#FFFFFF`、正文 `#1C1C1C`、次要文字 `#6B6B6B`、分隔线 `#EEEEEE`、强调色 `#0F766E`、输入框边框 `#8F8F8F`。内容列最大宽度 720px，左右留白 24px。
- 字体 MUST 使用系统字体栈（`-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`），MUST NOT 加载 Google Fonts 或任何外部 CDN 资源。
- 首页视频文件 MUST 为 H.264（High profile、yuv420p）的非分片 MP4，moov 位于 mdat 之前（`-movflags +faststart`），MUST NOT 带音轨，关键帧间隔 1 秒；MUST 提供首帧封面图 `home.jpg` 作为 `poster`。原文件是 AV1 编码的分片 DASH 片段，部分设备无法硬件解码，打开和循环时会卡顿，已用 ffmpeg 以 CRF 27 转码（546KB，与原片 SSIM 0.987）。
- 首页视频 MUST 带 `autoplay muted loop playsinline`；系统开启"减少动态效果"（`prefers-reduced-motion: reduce`）时 MUST 暂停视频，用几行内联脚本实现。
- 可点击元素的点击区域 MUST 不小于 44px 高；文字对比度 MUST 不低于 4.5:1；所有输入框 MUST 有对应的 `<label>`。

### 6. 会话、登录与 CSRF

- MUST 使用 Starlette `SessionMiddleware`（签名 cookie，`same_site="lax"`），密钥为 `SECRET_KEY`。会话里只存两项：`csrf`（令牌）和 `admin`（布尔）。
- CSRF：首次需要时用 `secrets.token_urlsafe(32)` 生成并存入会话。表单放隐藏字段 `csrf_token`；`write.js` 发起的 `fetch` 放请求头 `X-CSRF-Token`。校验 MUST 用 `hmac.compare_digest`。
- 受保护的 POST MUST 先检查登录状态、再检查 CSRF，任一失败返回 403，且 MUST 在读取或保存上传文件之前完成。受保护的 GET 未登录时 303 到 `/login?next=<路径>`。
- 登录：用户名用 `hmac.compare_digest` 比较；无论用户名是否正确 MUST 都执行一次密码哈希校验，避免通过响应时间判断用户名。登录成功后 MUST 清空会话并重新生成 CSRF 令牌。
- `next` 只接受以单个 `/` 开头、且不以 `//` 或 `/\` 开头的路径，否则用 `/write`。
- 退出只接受 POST。
- 密码哈希 MUST 用 `hashlib.scrypt`（随机 16 字节盐），存储格式 `scrypt$n$r$p$<salt_b64>$<hash_b64>`。`python -m app.passwords` 用 `getpass` 读入密码并输出哈希。
- 备选：starlette-csrf 等第三方库。放弃理由：标准库十几行即可。

### 7. 写作

- `/write` 和 `/post/<id>/edit` 共用模板 `write.html`。提交字段：`title`、`body`、`cover`（文件，可选）、`remove_cover`（复选框）、`action`（`draft` 或 `publish`，"更新"对应 `publish`、"转为草稿"对应 `draft`）、`csrf_token`。
- 表单 MUST 用 `multipart/form-data`。校验失败返回 400 时，模板 MUST 回填标题和正文。
- 预览：`write.js` 在切到"预览"时把正文 POST 到 `/preview`，把返回的 HTML 片段放进预览区；切回"编辑"只是切换显示，文本框内容不动。
- 插图：`write.js` 用隐藏的 `<input type="file">` 响应"插入图片"按钮，并监听正文框的 `paste` 事件读取剪贴板中的图片文件，POST 到 `/uploads`，成功后在 `selectionStart` 处插入 `![](url)`（不在行首时前补换行、后面不是换行时后补换行，让图片单独成行，避免破坏行首的 `#`、`-`、```` ``` ```` 等标记；不替换选中文字），用按钮插图时先切回编辑模式；预览只采用最近一次请求的结果，失败时把错误写进一个 `aria-live="polite"` 的提示区。
- 删除文章与评论用普通表单 POST，表单 `onsubmit` 调用 `confirm()`。
- 不开启 JS 时，标题、正文、封面、保存和发布仍可用；预览和插图需要 JS。

### 8. 图片

- 大小：MUST 最多读取 10 MB + 1 字节，超过即拒绝，不读入整个文件。
- 识别：MUST 用 Pillow 打开字节流，`format` 必须属于 `JPEG`、`PNG`、`GIF`、`WEBP`，并调用 `verify()`；把 `Image.DecompressionBombWarning` 视为错误，捕获 `DecompressionBombError`。任何异常都按"不是有效图片"拒绝。
- 去元数据：静态的 JPEG、PNG、WebP MUST 用 Pillow 重新编码保存，不写入 EXIF 等元数据（JPEG 先按 EXIF 方向用 `ImageOps.exif_transpose` 转正，质量 90）；GIF 和动图按原字节保存。
- 保存路径：`MEDIA_ROOT/covers/` 或 `MEDIA_ROOT/uploads/`，下分 `YYYY/MM/`，文件名 `secrets.token_hex(16)` 加由格式决定的扩展名。
- `/media` MUST 用 `StaticFiles` 挂载，目录在启动时创建。
- 删除封面时 MUST 确认解析后的路径位于 `MEDIA_ROOT` 内，文件不存在时忽略。
- 正文插图不追踪引用关系，删除文章时不删除（见 Non-Goals）。

### 9. 配置

- `config.py` 在导入时读取 `SECRET_KEY`、`ADMIN_USERNAME`、`ADMIN_PASSWORD_HASH`，缺失或为空 MUST 抛出包含变量名的错误，阻止启动。
- MUST NOT 在代码、测试或文档中写入真实密钥；测试 MUST 通过 fixture 设置假的环境变量。
- 会话 cookie 的 `https_only` 不在本次处理（部署属于 Non-Goals），README 中注明上线时应开启。

### 10. 测试

- 用 pytest + FastAPI `TestClient`（依赖 httpx2 2.16.0。Starlette 1.9 的 TestClient 优先使用 httpx2，对旧的 httpx 发出弃用警告；httpx2 由 Pydantic 团队维护，用户已批准引入）。每个 spec Scenario MUST 至少对应一个测试用例，测试名或 docstring 注明对应的 Scenario。
- 测试图片 MUST 在测试中用 Pillow 现场生成（含带 GPS EXIF 的 JPEG），不提交二进制样本。
- `write.js` 的浏览器内行为（切换、粘贴、插入）没有自动化测试，在任务 6.4 人工检查。

### 11. 清理

- 新版全部测试通过后，MUST 删除 `manage.py`、`django_web/`、`blog/`（静态视频先移到 `app/static/videos/`），以及不再引用的 `item1.jpg`、`item2.jpg`。
- `.gitignore` MUST 增加 `blog.db`，保留 `media/`，删除仅针对 Django 的条目。
- 新增简短的 `README.md`，写明 Python 版本要求、安装、生成密码哈希、设置环境变量、启动命令、上线注意事项。

## Risks / Trade-offs

- [登录没有频率限制，可被暴力破解] → 属于 Non-Goals；scrypt 让每次尝试有一定成本；README 提示使用强密码，上线时可在反向代理层限流。
- [重新编码会轻微降低 JPEG 画质] → 质量设为 90；为了不泄露照片里的 GPS 位置，接受这个代价。
- [正文插图不清理，长期会留下无用文件] → 文件量小，属于 Non-Goals；以后需要时再加清理脚本。
- [预览和插图依赖 JS，`write.js` 没有自动化测试] → 后端接口都有测试；JS 只做调用和插入，逻辑很少，人工检查覆盖。
- [SQLite 不存时区，若有代码写入本地时间会导致显示偏移] → 统一由模型默认值写 UTC，并有跨日显示测试。
- [去掉 Bootstrap 后需自写全部样式，移动端可能出现布局问题] → 只用单栏布局；实现后在 390px 宽度下人工检查全部页面。
- [删除 `item1.jpg`、`item2.jpg`] → 仍可从 git 历史恢复；若用户在 review 时要求保留，则改为只移入 `app/static/` 不引用。

## Migration Plan

1. 在 `feat/fastapi-migration` 分支实现新版，期间 Django 代码保持不动。
2. 新版测试全部通过，并人工检查页面后，删除 Django 代码。
3. 线上从空库启动：设置环境变量，启动 uvicorn，访问 `/login` 登录后在 `/write` 重新发布文章。
4. 回滚：切回 `main` 分支即为原 Django 版本；新旧数据库文件名不同（`blog.db` 与 `db.sqlite3`），互不影响。
