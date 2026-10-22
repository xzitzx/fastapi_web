# admin-auth Specification

## Purpose
站长身份：用环境变量配置唯一的站长账号，提供登录与退出，并保证写作、删除、上传等操作只有登录后才能执行。

## Requirements

### Requirement: 必要配置
系统启动时 MUST 读取环境变量 `SECRET_KEY`、`ADMIN_USERNAME`、`ADMIN_PASSWORD_HASH`。任一缺失或为空时，系统 MUST 拒绝启动，并给出指明缺失变量名的错误信息。代码仓库中 MUST NOT 包含任何密钥或明文密码。

#### Scenario: 缺少 SECRET_KEY
- **WHEN** 未设置 `SECRET_KEY` 时启动应用
- **THEN** 启动失败，错误信息包含 `SECRET_KEY`

### Requirement: 生成密码哈希
系统 SHALL 提供一个命令行入口，读取站长输入的密码（输入时不回显），输出可直接填入 `ADMIN_PASSWORD_HASH` 的哈希字符串。同一密码两次生成的哈希 SHALL 不同（带随机盐），且都能通过校验。

#### Scenario: 生成并校验
- **WHEN** 站长用该命令为密码 P 生成哈希 H
- **THEN** 用 H 校验 P 成功，校验其他密码失败

### Requirement: 登录
`/login` SHALL 显示登录表单（用户名、密码、隐藏的 CSRF 令牌）。用户名和密码都正确时，系统 SHALL 建立登录状态并以 303 重定向：查询参数 `next` 是本站路径（以单个 `/` 开头，不以 `//` 或 `/\` 开头）时跳到该路径，否则跳到 `/write`。用户名或密码错误时 MUST NOT 建立登录状态，SHALL 返回 400，提示"用户名或密码错误"，保留已填的用户名，MUST NOT 回填密码。CSRF 令牌缺失或不匹配时 SHALL 返回 403。已登录时访问 `/login` SHALL 以 303 重定向到 `/write`。

#### Scenario: 登录成功
- **WHEN** 访客在 `/login` 提交正确的用户名和密码
- **THEN** 返回 303 重定向到 `/write`，之后访问 `/write` 返回 200

#### Scenario: 密码错误
- **WHEN** 访客提交正确的用户名和错误的密码
- **THEN** 状态码为 400，页面提示"用户名或密码错误"，用户名输入框保留原值，密码输入框为空，之后访问 `/write` 仍被重定向到登录页

#### Scenario: 登录后回到原页面
- **WHEN** 访客在 `/login?next=/post/3/edit` 提交正确的用户名和密码
- **THEN** 返回 303 重定向到 `/post/3/edit`

#### Scenario: 拒绝站外跳转
- **WHEN** 访客在 `/login?next=//evil.example` 提交正确的用户名和密码
- **THEN** 返回 303 重定向到 `/write`

#### Scenario: 已登录访问登录页
- **WHEN** 已登录的站长请求 `/login`
- **THEN** 返回 303 重定向到 `/write`

### Requirement: 退出登录
站长 SHALL 能通过 POST `/logout`（带有效 CSRF 令牌）退出登录，系统 SHALL 清除登录状态并以 303 重定向到 `/`。GET `/logout` MUST NOT 退出登录。

#### Scenario: 退出
- **WHEN** 已登录的站长提交退出表单
- **THEN** 返回 303 重定向到 `/`，之后访问 `/write` 被重定向到登录页

#### Scenario: GET 请求不能退出
- **WHEN** 已登录的站长发起 GET `/logout`
- **THEN** 登录状态保持不变

### Requirement: 受保护操作的访问控制
未登录时，对 `/write`、`/post/<id>/edit` 的 GET 请求 SHALL 以 303 重定向到 `/login?next=<原路径>`；对 `/write`、`/post/<id>/edit`、`/post/<id>/delete`、`/comments/<id>/delete`、`/preview`、`/uploads` 的 POST 请求 SHALL 返回 403，且 MUST NOT 修改任何数据或保存任何文件。已登录时，这些 POST 请求 MUST 携带有效 CSRF 令牌（表单字段或 `X-CSRF-Token` 请求头），否则 SHALL 返回 403 且不做任何修改。

#### Scenario: 未登录打开写作页
- **WHEN** 未登录的访客请求 `/write`
- **THEN** 返回 303 重定向到 `/login?next=/write`

#### Scenario: 未登录删除文章
- **WHEN** 未登录的请求 POST `/post/1/delete`
- **THEN** 状态码为 403，文章仍然存在

#### Scenario: 未登录上传图片
- **WHEN** 未登录的请求向 `/uploads` 上传一张图片
- **THEN** 状态码为 403，上传目录中没有新文件

#### Scenario: 登录后缺少 CSRF 令牌
- **WHEN** 已登录的站长不带 CSRF 令牌 POST `/post/1/delete`
- **THEN** 状态码为 403，文章仍然存在
