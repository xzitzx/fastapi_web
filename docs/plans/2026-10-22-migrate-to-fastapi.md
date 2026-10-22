# 迁移到 FastAPI 实施计划

**目标**：按 OpenSpec 变更 `migrate-to-fastapi` 把站点从 Django 重写为 FastAPI，实现简约风前台、自建登录与写作页。

**任务来源**：`openspec/changes/migrate-to-fastapi/tasks.md`。**测试来源**：`openspec/changes/migrate-to-fastapi/specs/*/spec.md` 的每个 Scenario。**技术约束**：同目录 `design.md`。**非目标**：同目录 `proposal.md` 的 Non-Goals 段，越界即停止。

**视觉稿**：claude.ai artifact `6HJpc2DVCSXxczH9zNzzSa`（"博客简约风预览"）中的 `Video.dc.html`（首页）、`List.dc.html`、`Post.dc.html`、`Write.dc.html`、`Login.dc.html`。这些是设计稿，取其中的结构、间距、字号、颜色，写成普通 HTML + `site.css`；`{{accent}}` 一律为 `#0F766E`；稿中的示例文字、`[封面图]` 等占位不要照搬。

---

## Global Constraints

适用于每个任务，任务内不得放宽。

**运行环境**
- Python：项目根目录 `.venv`，由 `/opt/homebrew/bin/python3.12` 创建，已装好下列依赖。所有命令用 `.venv/bin/python`、`.venv/bin/pytest`、`.venv/bin/pygmentize`。最低支持 Python 3.11。
- 运行依赖，`requirements.txt` 必须恰好是这些行（UTF-8，`==` 锁定）：`fastapi==0.159.1`、`starlette==1.9.0`、`uvicorn==0.54.0`、`jinja2==3.1.6`、`python-multipart==0.0.32`、`itsdangerous==2.2.0`、`sqlalchemy==2.1.6`、`pillow==13.0.0`、`markdown==3.11.2`、`pygments==2.21.0`。
- 测试依赖，`requirements-dev.txt`：第一行 `-r requirements.txt`，然后 `pytest==9.1.1`、`httpx2==2.16.0`（Starlette 1.9 的 TestClient 依赖它；不得安装旧的 `httpx`）。
- 禁止安装或引入任何其他 Python 包、JS 库、CSS 框架、外部字体或 CDN 资源。需要新依赖时停止并报告。

**目录与命名**
- 应用包 `app/`，模块：`config.py`、`db.py`、`models.py`、`passwords.py`、`security.py`、`templating.py`、`rendering.py`、`images.py`、`main.py`、`routes/__init__.py`、`routes/pages.py`、`routes/auth.py`、`routes/authoring.py`。
- 模板 `app/templates/`：`base.html`、`home.html`、`post_list.html`、`post_detail.html`、`login.html`、`write.html`、`404.html`、`_preview.html`。
- 静态 `app/static/`：`css/site.css`、`css/code.css`、`js/write.js`、`videos/home.mp4`。
- 测试 `tests/`，配置 `pytest.ini`（项目根目录）。
- 应用对象：`app.main:app`。

**URL（精确）**
- 前台：`GET /`、`GET /blog/`、`GET /post/{post_id}/`、`POST /post/{post_id}/`（评论）。
- 身份：`GET /login`、`POST /login`、`POST /logout`。
- 写作：`GET /write`、`POST /write`、`GET /post/{post_id}/edit`、`POST /post/{post_id}/edit`、`POST /post/{post_id}/delete`、`POST /comments/{comment_id}/delete`、`POST /preview`、`POST /uploads`。
- 挂载：`/static` → `app/static`，`/media` → `settings.media_root`。
- `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`。

**配置**
- 必填环境变量：`SECRET_KEY`、`ADMIN_USERNAME`、`ADMIN_PASSWORD_HASH`。可选：`DATABASE_URL`（默认 `sqlite:///<项目根>/blog.db`）、`MEDIA_ROOT`（默认 `<项目根>/media`）。

**会话与 CSRF**
- `SessionMiddleware(secret_key=settings.secret_key, same_site="lax")`，其余参数用默认值。
- 会话键只有：`"csrf"`、`"admin"`。表单字段名 `csrf_token`，请求头 `X-CSRF-Token`。
- 受保护的 POST 路由：函数签名里不得声明 `Form`/`File` 参数；函数体第一步 `require_admin(request)`，第二步 `await require_csrf(request)`，之后才解析表单、查库、处理文件。

**数据**
- 表名 `posts`、`comments`。`Post.status` 取值只有 `"draft"`、`"published"`，约束名 `ck_posts_status`。
- 时间一律 `datetime.now(timezone.utc)` 写入；读取时 naive 值视为 UTC。

**确切取值**
- 每页 5 篇；首页 5 篇；摘要 100 字符，超出加 `…`（U+2026）；阅读速度 400 字符/分钟，最少 1。
- 昵称 1 到 80 字符，评论内容 1 到 2000 字符，标题 1 到 200 字符（均为去除首尾空白后）。
- 图片上限 `10 * 1024 * 1024` 字节；格式 `JPEG`→`jpg`、`PNG`→`png`、`GIF`→`gif`、`WEBP`→`webp`；JPEG/WebP 重编码质量 90。
- scrypt：`n=16384`、`r=8`、`p=1`、盐 16 字节、`dklen=64`；格式 `scrypt$16384$8$1$<base64 盐>$<base64 哈希>`（标准 base64）。
- 时区 `Asia/Shanghai`；日期格式：列表与首页 `%Y-%m-%d`，详情 `%Y年%m月%d日`，评论与"最后保存于" `%Y-%m-%d %H:%M`。
- Markdown 扩展 `["extra", "codehilite", "toc"]`。代码高亮主题 `xcode`。
- 颜色：背景 `#FFFFFF`、正文 `#1C1C1C`、次要文字 `#6B6B6B`、分隔线 `#EEEEEE`、强调色 `#0F766E`、输入框边框 `#8F8F8F`、代码块背景 `#F6F6F6`。内容列 `max-width: 720px`，左右内边距 24px。字体栈 `-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif`。

**界面文字（精确）**
- 导航：`首页`、`文章`；登录后追加 `写文章`、`退出`。页脚 `© {年份}`。
- 前台：`最近文章`（首页 h1）、`还没有文章`、`全部文章 →`、`上一页`、`下一页`、`{当前} / {总数}`、`约 {N} 分钟`、`{N} 条评论`、`草稿`、`最后保存于 {时间}`、`返回文章列表`、`上一篇`、`下一篇`、`没有了`、`评论`、`还没有评论`、`发表评论`、`昵称`、`内容`、`提交评论`、`编辑`、`删除`、`页面不存在`、`返回首页`。
- 登录：`登录`、`用户名`、`密码`、`用户名或密码错误`。
- 写作：`标题`、`封面图（可选）`、`JPG、PNG、GIF、WebP，不超过 10MB`、`移除封面`、`正文`、`支持 Markdown。图片可以点"插入图片"上传，也可以直接粘贴到正文里。`、`编辑`、`预览`、`插入图片`、`保存草稿`、`发布`、`更新`、`转为草稿`、`没有内容`；编辑页状态 `草稿 · 最后保存于 {时间}` 或 `已发布 · 最后保存于 {时间}`。
- 错误提示：`昵称不能为空`、`昵称不能超过 80 个字符`、`内容不能为空`、`内容过长，最多 2000 个字符`、`标题不能为空`、`标题过长，最多 200 个字符`、`正文不能为空`、`封面图需要重新选择`、`图片不能超过 10MB`、`只支持 JPG、PNG、GIF、WebP 图片`、`没有收到文件`、`预览失败，请重试`、`上传失败，请重试`。
- 删除确认框：`确定删除这篇文章？`、`确定删除这条评论？`。
- 无障碍标签（aria-label，不显示在页面上）：`主导航`、`向下滚动到最近文章`、`分页`、`上一篇和下一篇`、`切换编辑和预览`。
- 未登录访客看到的页面（`/login` 除外）不得出现：`我的博客`、`WELCOME`、`Powered by`、`注册`、`登录`、`/login`。

**工作方式**
- 严格 TDD：先写测试，运行确认失败（原因正确），再写最少代码让它通过，再重构。每个 spec Scenario 至少一个测试，docstring 写 `Scenario: <名称>`。
- `TestClient` 检查重定向时必须传 `follow_redirects=False`。
- 只改本任务列出的文件；不得修改 Django 代码（`manage.py`、`django_web/`、`blog/`），直到任务 P8；不得修改 `openspec/` 下的文件；不得 git commit。
- 有疑问、发现计划与源码实际 API 不符、或需要越出范围时，停止并在报告中说明，不要自行变通。
- 结束时报告：改动的文件清单、新增测试清单与对应 Scenario、`pytest` 完整输出的最后 20 行、未完成或有疑问的地方。

---

## P1 环境与骨架（tasks 1.1–1.3）

**Interfaces**
- 消费：无。
- 产出：
  - `app/config.py`：`BASE_DIR: Path`（项目根）；`@dataclass(frozen=True) class Settings(secret_key: str, admin_username: str, admin_password_hash: str, database_url: str, media_root: Path)`；`def load_settings(env: Mapping[str, str] = os.environ) -> Settings`，缺失或为空的必填变量全部列出，抛 `RuntimeError`，消息包含每个变量名；模块级 `settings = load_settings()`。
  - `app/passwords.py`（不 import 任何 `app.*`）：`hash_password(password: str) -> str`、`verify_password(password: str, encoded: str) -> bool`（格式错误返回 False，不抛异常，比较用 `hmac.compare_digest`）；`if __name__ == "__main__"`：`getpass` 读两次，不一致则输出错误并以状态 1 退出，一致则打印哈希。
  - `app/main.py`：`def create_app() -> FastAPI`、`app = create_app()`；创建 `settings.media_root` 目录后挂载 `/static`、`/media`；lifespan 中调用 `app.db.init_db()`（P2 之前用空实现占位并在 P2 替换）。
  - `pytest.ini`：`testpaths = tests`。
  - `tests/conftest.py`：在 import `app.main` 之前，用 `tempfile.mkdtemp()` 建临时目录，设置 `SECRET_KEY`、`ADMIN_USERNAME=admin`、`ADMIN_PASSWORD_HASH`（用 `app.passwords.hash_password(TEST_PASSWORD)` 生成，`TEST_PASSWORD = "test-password"`）、`DATABASE_URL`、`MEDIA_ROOT`；fixture `client`（`with TestClient(app) as c`）。
- 测试：`tests/test_config.py`（"缺少 SECRET_KEY"：调用 `load_settings({...})` 断言抛错且消息含 `SECRET_KEY`）、`tests/test_passwords.py`（"生成并校验"，以及格式错误返回 False）、`tests/test_app.py`（"请求接口文档"：`/docs`、`/redoc`、`/openapi.json` 均 404）。
- 说明：spec "生成并校验"归属 tasks 3.1，提前到 P1 是因为 conftest 需要它。

## P2 数据与渲染（tasks 2.1–2.2）

**Interfaces**
- 消费：`app.config.settings`。
- 产出：
  - `app/db.py`：`class Base(DeclarativeBase)`；`engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})`；连接事件里执行 `PRAGMA foreign_keys=ON`；`SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)`；`def get_db() -> Iterator[Session]`；`def init_db() -> None`（import models 后 `create_all`）。
  - `app/models.py`：`STATUS_DRAFT = "draft"`、`STATUS_PUBLISHED = "published"`、`def utcnow() -> datetime`；`Post`（id、title、body 默认 `""`、cover、status 默认 draft、created_at、updated_at（`onupdate=utcnow`）、published_at，`comments` 关系 `cascade="all, delete-orphan"`、按 `created_at, id` 排序；方法 `publish(self) -> None`：设为 published，`published_at` 为空时写入 `utcnow()`；`is_published` 属性）；`Comment`（id、post_id 外键 `ondelete="CASCADE"` 且建索引、name、body、created_at，`post` 关系）。
  - `app/rendering.py`：`TZ`；`render_markdown(text: str) -> markupsafe.Markup`；`excerpt(text: str, length: int = 100) -> str`（渲染后去标签、`html.unescape`、空白折叠为单个空格）；`reading_minutes(text: str) -> int`；`to_local(dt: datetime) -> datetime`；`fmt_date(dt)`、`fmt_date_cn(dt)`、`fmt_datetime(dt)` 返回 str；`current_year(now: datetime | None = None) -> int`。
  - `tests/conftest.py` 增加：autouse fixture 每个测试前 `drop_all` + `create_all`、清空 `MEDIA_ROOT`；fixture `db`（`SessionLocal()`）；fixture `make_post(title="标题", body="正文", status="published", published_at=None, created_at=None)`，发布状态未给时间则用 `utcnow()`。
- 测试：`tests/test_models.py`（创建；`updated_at` 自动更新；删除文章连带评论；非法 status 抛 `IntegrityError`；`publish()` 不覆盖已有 `published_at`）、`tests/test_rendering.py`（"1000 字正文"、"极短正文"、"跨日的时间"、摘要不含 `##` 和反引号且超长时以 `…` 结尾）。

## P3 身份与安全（tasks 3.1–3.3）

**Interfaces**
- 消费：`settings`、`passwords.verify_password`、`rendering.current_year`、`db.get_db`。
- 产出：
  - `app/security.py`：常量 `SESSION_CSRF = "csrf"`、`SESSION_ADMIN = "admin"`、`CSRF_FIELD = "csrf_token"`、`CSRF_HEADER = "X-CSRF-Token"`；`get_csrf_token(request) -> str`（没有就用 `secrets.token_urlsafe(32)` 生成并存入会话）；`csrf_valid(request, token: str | None) -> bool`；`is_admin(request) -> bool`；`check_credentials(username: str, password: str) -> bool`（用户名和密码两项都计算后再合并结果）；`log_in(request)`（清空会话、置 admin、新 CSRF）；`log_out(request)`；`safe_next(value: str | None) -> str`；`class LoginRequired(Exception)`（属性 `next_path`）；`require_admin_page(request) -> None`（未登录抛 `LoginRequired(路径+查询串)`）；`require_admin(request) -> None`（未登录抛 `HTTPException(403)`）；`async require_csrf(request) -> None`（先看请求头，没有再 `await request.form()` 取字段，不通过抛 `HTTPException(403)`）。
  - `app/templating.py`：`templates = Jinja2Templates(directory=...)`；注册过滤器 `date`、`date_cn`、`datetime_local` 对应 rendering 的三个格式化函数；`render(request, name: str, context: dict | None = None, status_code: int = 200) -> Response`，自动注入 `is_admin`（bool）、`csrf_token`（可调用，模板里写 `{{ csrf_token() }}`，只在用到时才生成令牌）、`year`。
  - `app/templates/base.html`：块 `title`、`content`、`scripts`；按 spec 渲染导航（登录后的"退出"是 POST `/logout` 的表单按钮）和页脚；引用 `/static/css/site.css`（此时可为空文件，P4 补全）。
  - `app/templates/login.html`、`app/routes/auth.py`（`router`）：GET 已登录 303 到 `/write`；POST 先校验 CSRF，再校验凭据，`next` 取查询参数并经 `safe_next`；失败 400 回填用户名。`POST /logout`：校验 CSRF，`log_out`，303 到 `/`。
  - `app/routes/authoring.py`（`router`）：按 URL 清单声明全部写作路由。本任务中 GET 路由只做 `require_admin_page` 后返回 200 占位文本，POST 路由只做 `require_admin` + `await require_csrf` 后返回 501；P6、P7 替换为真实实现。
  - `app/main.py`：加 `SessionMiddleware`；include 两个 router；`LoginRequired` 处理器返回 303 到 `/login?next=` + `quote(next_path, safe="/")`。
  - `tests/conftest.py` 增加：`csrf_from(html: str) -> str`（取隐藏字段值）、fixture `admin_client`（GET `/login` 取令牌后 POST 登录）。
- 测试：`tests/test_auth.py` 覆盖 admin-auth 中 "登录"、"退出登录"、"受保护操作的访问控制" 三个 Requirement 的全部 Scenario；"未登录上传图片"断言 `MEDIA_ROOT` 下没有文件。

## P4 前台页面（tasks 4.1–4.5）

**Interfaces**
- 消费：P2 的模型与渲染函数、P3 的 `render`、`is_admin`、`base.html`。
- 产出：
  - `app/static/css/site.css`：按 Global Constraints 的颜色、字体、宽度；所有可点击元素高度不小于 44px；评论内容 `white-space: pre-line`；`.codehilite` 背景 `#F6F6F6`、圆角 8px、`overflow-x: auto`。
  - `app/static/css/code.css`：执行 `.venv/bin/pygmentize -S xcode -f html -a .codehilite > app/static/css/code.css` 生成，不手改。
  - `app/static/videos/home.mp4`：从 `blog/static/blog/videos/VID_20250731_031214_786.mp4` 复制（不删原文件）。
  - `app/routes/pages.py`（`router`）：`GET /`、`GET /blog/`、`GET /post/{post_id}/`。列表评论数用一次 `outerjoin` + `group_by` 查询；分页按 spec 自行实现；上一篇/下一篇按 `(published_at, id)` 比较；草稿对访客 404。
  - 模板 `home.html`（视频 + 内联脚本：`prefers-reduced-motion: reduce` 时暂停并移除 autoplay；向下滚动箭头链接 `#recent`，带 `aria-label`）、`post_list.html`（登录后草稿区）、`post_detail.html`（引入 `code.css`；登录后编辑/删除按钮，删除表单 `onsubmit="return confirm('确定删除这篇文章？')"`；本任务先不做评论区，留给 P5）、`404.html`。
  - `app/main.py`：`StarletteHTTPException` 处理器（404 渲染 `404.html`，其余交给 `fastapi.exception_handlers.http_exception_handler`）；`RequestValidationError` 处理器同样返回 404 页（路径参数不是整数时）。
- 测试：`tests/test_layout.py`（页面框架 Requirement 全部 Scenario；"页脚只显示年份"通过 monkeypatch 当前时间或断言等于 `current_year()`）、`tests/test_home.py`、`tests/test_list.py`（含"登录后看到草稿"）、`tests/test_detail.py`（含"Markdown 渲染"、草稿可见性、管理按钮；`/post/abc/` 返回 404）、`tests/test_404.py`（"文章不存在"、"已删除的旧路由"）。

## P5 评论（tasks 5.1–5.3）

**Interfaces**
- 消费：P4 的详情页与 `pages.router`、P3 的 `require_csrf`、`csrf_valid`、`require_admin`。
- 产出：
  - `pages.py` 增加 `POST /post/{post_id}/`：顺序为查文章（不存在或草稿 404）→ CSRF（403）→ 校验（400，重新渲染详情页并回填）→ 保存 → 303 到 `/post/{post_id}/`。不声明 `Form` 参数，用 `await request.form()`。
  - `post_detail.html` 增加评论列表、评论数、评论表单（仅已发布文章）、登录后每条评论的删除表单（`onsubmit` 确认）。
  - `authoring.py` 的 `POST /comments/{comment_id}/delete` 改为真实实现：不存在 404，删除后 303 到所属文章详情页。
- 测试：`tests/test_comments.py` 覆盖 comments spec 全部 Scenario。"提交脚本标签"之前先确认 `starlette/templating.py` 第 95 行附近 `select_autoescape()` 对 `.html` 生效，在报告中写明确认结果。

## P6 写作：页面、保存、封面（tasks 6.1–6.4）

**Interfaces**
- 消费：P2 模型（`publish()`）、P3 安全函数与 `render`、`authoring.router` 占位路由。
- 产出：
  - `app/images.py`：`MAX_BYTES`；`ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "GIF": "gif", "WEBP": "webp"}`；`class InvalidImage(Exception)`（消息为界面错误文字）；`process_image(data: bytes) -> tuple[bytes, str]`（大小、`Image.open`、`verify()`、`DecompressionBombWarning` 视为错误；静态 JPEG/PNG/WebP 经 `ImageOps.exif_transpose` 后重编码且不写 EXIF，GIF 与动图原样返回）；`async save_image(upload: UploadFile, kind: Literal["covers", "uploads"]) -> str`（最多读 `MAX_BYTES + 1` 字节；路径 `{kind}/{YYYY}/{MM}/{secrets.token_hex(16)}.{ext}`，返回相对 `MEDIA_ROOT` 的路径）；`media_url(rel: str) -> str` 返回 `"/media/" + rel`；`delete_media(rel: str | None) -> None`（解析后必须位于 `MEDIA_ROOT` 内，文件不存在时忽略）。
  - `write.html`：按视觉稿；`<form method="post" enctype="multipart/form-data">`；字段 `title`、`body`（`id="post-body"`）、`cover`、`remove_cover`（仅有封面时出现，值 `1`）、`action`（两个提交按钮 `name="action"`，值 `draft` / `publish`）、`csrf_token`；预览区 `id="preview"`（默认隐藏）；切换按钮 `data-mode="edit"` / `data-mode="preview"`（带 `aria-pressed`）；"插入图片"按钮 `id="insert-image"`；隐藏文件框 `id="image-file"`（`accept="image/jpeg,image/png,image/gif,image/webp"`）；提示区 `id="editor-message"`（`aria-live="polite"`）；编辑页显示状态与"最后保存于"；页面底部引用 `/static/js/write.js`（文件在 P7 创建，本任务先建空文件）。
  - `authoring.py`：`GET /write`、`GET /post/{post_id}/edit`、`POST /write`、`POST /post/{post_id}/edit` 真实实现。校验顺序：文字字段 → 封面（仅当文件名非空且有内容）→ 写库 → 提交后删除被替换或移除的旧封面。失败返回 400 并回填，选了封面时附加"封面图需要重新选择"。成功：`draft` 303 到编辑页，`publish` 303 到详情页。
- 测试：`tests/test_images.py`（图片校验与去元数据 Requirement 全部 Scenario；测试图片用 Pillow 现场生成，GPS EXIF 用 `Image.Exif()` 写入 `0x8825`）、`tests/test_write.py`（写作页、保存草稿、发布、校验失败、封面 Requirement 全部 Scenario；"重新发布保留原发布时间"直接改库造出 T1 再操作）。

## P7 写作：预览、插图、删除、前端脚本（tasks 6.5–6.7）

**Interfaces**
- 消费：P6 的 `images.py`、`write.html` 的元素 id、P3 安全函数。
- 产出：
  - `authoring.py`：`POST /preview`（字段 `body`，空白返回含 `没有内容` 的片段，否则用 `render_markdown` 渲染 `_preview.html`）；`POST /uploads`（CSRF 走请求头；字段 `file`；成功 `{"url": ...}`，失败 400 `{"error": ...}`）；`POST /post/{post_id}/delete`（删除评论、封面文件，303 到 `/blog/`；不存在 404）。
  - `app/static/js/write.js`：原生 JS，无依赖，`"use strict"`；从表单隐藏字段读 CSRF 令牌放入 `X-CSRF-Token` 请求头；切换编辑和预览（更新 `aria-pressed`、显示隐藏；切到预览时 POST `/preview`）；"插入图片"按钮触发 `#image-file`；正文框 `paste` 事件中取第一个图片文件上传；上传成功后在 `selectionStart` 处插入 `![](url)` 并恢复光标；失败把 `error` 写进 `#editor-message`。
- 测试：`tests/test_preview.py`、`tests/test_uploads.py`（"上传插图"后用返回的 url GET 得到 200）、`tests/test_write.py` 增加删除文章 Scenario。`write.js` 没有自动化测试，在报告中说明。

## P8 清理与收尾（tasks 7.1–7.3）

**Interfaces**
- 消费：全部前序产出。
- 产出：
  - 删除 `manage.py`、`django_web/`（项目内的 Django 配置包）、`blog/`（含 `item1.jpg`、`item2.jpg` 和原视频）。删除前先 `git status` 确认这些路径没有未提交的改动。
  - `.gitignore`：新增 `blog.db`；保留 `media/`、`.venv`；删除只针对 Django 的条目（`db.sqlite3`、`staticfiles/`、`local_settings.py`、`settings_local.py`、注释掉的 migrations 段）。
  - `README.md`：Python 版本要求；建虚拟环境与安装；`python -m app.passwords` 生成哈希；三个必填环境变量与两个可选变量；启动命令 `.venv/bin/uvicorn app.main:app --reload`；上线注意：设置 `https_only`、用反向代理限制请求体大小和登录频率、使用强密码。
- 验证：`git ls-files` 与工作区中不再有 Django 文件；`grep -rni "django" app tests requirements*.txt README.md` 无结果；按 README 在临时目录新建虚拟环境，从零安装并启动，`curl` 首页返回 200；`pytest` 全部通过；用脚本逐条核对每个 spec Scenario 名称都出现在某个测试的 docstring 中。
