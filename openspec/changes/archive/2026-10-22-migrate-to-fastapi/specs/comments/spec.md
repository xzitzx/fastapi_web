## Purpose

访客评论：让访客无需登录，在文章详情页填写昵称和内容发表评论，保证提交安全、展示安全，并让站长能删除不当评论。

## ADDED Requirements

### Requirement: 评论展示
已发布文章的详情页 SHALL 显示"评论"标题和评论总数，并按评论时间正序列出该文章的全部评论；每条评论 SHALL 显示昵称、北京时间（`YYYY-MM-DD HH:MM`）和内容，内容中的换行 SHALL 保留为换行。没有评论时 SHALL 显示"还没有评论"。

#### Scenario: 两条评论
- **WHEN** 文章有两条评论，先后发表
- **THEN** 详情页显示评论数 2，先发表的排在前面

#### Scenario: 多行内容
- **WHEN** 评论内容为"第一行\n第二行"
- **THEN** 页面上两行分开显示

### Requirement: 发表评论
已发布文章的详情页 SHALL 提供评论表单，包含昵称、内容和隐藏的 CSRF 令牌。访客向 `/post/<id>/` 提交 POST 且数据有效时，系统 SHALL 保存评论并以 303 重定向到 `/post/<id>/`。

#### Scenario: 提交成功
- **WHEN** 访客提交昵称"小李"、内容"写得好"和有效的 CSRF 令牌
- **THEN** 系统保存评论，返回 303 并重定向到该文章详情页，页面上出现这条评论

#### Scenario: 文章不存在
- **WHEN** 访客向不存在的文章提交评论
- **THEN** 状态码为 404，不保存任何评论

#### Scenario: 向草稿提交评论
- **WHEN** 任何人向一篇草稿的 `/post/<id>/` 提交评论
- **THEN** 状态码为 404，不保存任何评论

### Requirement: 评论校验
昵称去除首尾空白后 MUST 为 1 到 80 个字符；内容去除首尾空白后 MUST 为 1 到 2000 个字符。校验失败时系统 MUST NOT 保存评论，SHALL 返回状态码 400，重新渲染详情页，显示错误提示并保留访客已填写的内容。

#### Scenario: 昵称为空
- **WHEN** 访客提交的昵称只有空格
- **THEN** 状态码为 400，页面提示昵称不能为空，评论未保存

#### Scenario: 内容过长
- **WHEN** 访客提交 2001 个字符的内容
- **THEN** 状态码为 400，页面提示内容过长，表单中保留已填写的昵称和内容

### Requirement: CSRF 防护
评论提交 MUST 携带与访客会话匹配的 CSRF 令牌。令牌缺失或不匹配时系统 MUST NOT 保存评论，SHALL 返回状态码 403。

#### Scenario: 缺少令牌
- **WHEN** 请求不带 CSRF 令牌直接 POST 到 `/post/<id>/`
- **THEN** 状态码为 403，评论未保存

#### Scenario: 令牌不匹配
- **WHEN** 请求携带的令牌与会话中的令牌不同
- **THEN** 状态码为 403，评论未保存

### Requirement: 内容转义
昵称和内容 MUST 作为纯文本展示，其中的 HTML MUST 被转义，不得被浏览器当作标签执行。

#### Scenario: 提交脚本标签
- **WHEN** 访客提交内容 `<script>alert(1)</script>`
- **THEN** 详情页源码中出现转义后的 `&lt;script&gt;`，不出现原样的 `<script>alert(1)</script>`

### Requirement: 删除评论
站长登录后 SHALL 能通过 POST `/comments/<id>/delete`（带有效 CSRF 令牌）删除任意评论，成功后以 303 重定向回该评论所属文章的详情页。该操作的访问控制见 `admin-auth`。评论不存在时 SHALL 返回 404。

#### Scenario: 删除垃圾评论
- **WHEN** 已登录的站长删除一条评论
- **THEN** 返回 303 重定向到所属文章详情页，该评论不再出现，评论数减 1

#### Scenario: 评论不存在
- **WHEN** 已登录的站长删除一条不存在的评论
- **THEN** 状态码为 404
