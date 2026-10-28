# 反馈平台代码审计与修复报告（第二轮）

## 结论

本轮在第一轮修复版基础上继续进行深度审计，并直接修改代码、数据库约束、部署配置与回归测试。当前交付版本重点解决了权限边界、旧数据库迁移、状态机一致性、会话失效、密钥/默认口令、SQLite 约束、审计日志失败语义、请求限制及容器加固等问题。

审计覆盖约 **9,000+ 行** Python、Jinja2、CSS、Shell、Docker/Compose 与测试代码；当前项目包含 **31 个 Flask 路由、19 个模板、47 个回归测试方法、8 个 SQLite 触发器**。

> 说明：最终交付前已在安装完整依赖的环境中执行全部 47 个回归测试、19 个模板编译、旧库迁移探测、全路由动态探测与真实 Gunicorn 启动验证，结果见下文“实际验证结果”。

## 第二轮重点修复

### 1. 认证与权限

- 登录用户名改为大小写不敏感查询，与注册时的大小写不敏感唯一约束保持一致。
- 用户 ID 会话令牌加入 `auth_version`；修改密码后旧登录会话和 remember token 失效。
- 封禁用户、关闭游客功能时，已有不再合法的会话会被强制退出。
- 保留第一轮对子管理员横向越权的修复：子管理员不能编辑、封禁或解封管理员及其他子管理员。
- `admin` / `tourist` 系统账号角色不变量下沉到数据库触发器，避免绕过路由直接写库破坏角色边界。
- 用户名增加保留名、长度、字符与大小写冲突校验；数据库唯一索引作为第二道防线。
- 修改个人敏感信息/密码时要求当前密码。
- 登录后的 `next` 跳转拒绝外部 scheme/netloc、协议相对 URL 和反斜杠形式，防止开放重定向。

### 2. 数据库完整性与旧库迁移

SQLite 的 `ALTER TABLE ADD COLUMN` 不会自动给旧表补齐后来新增的外键，因此本轮没有仅依赖 ORM/建表声明，而是增加运行时迁移清理和数据库级触发器约束。

- 旧库初始化会修复：
  - 无效的 `post.deleted_by` / `comment.deleted_by` 引用；
  - 不存在、自引用或跨帖的父评论引用；
  - 删除帖、未审核/已拒绝游客帖上的非法“已采纳”状态；
  - `is_accepted = 0` 但仍残留 `accepted_by` 的状态。
- 若检测到无法安全自动修复的核心孤立数据，例如帖子作者不存在、评论作者或所属帖子不存在，则初始化明确失败，而不是带损坏数据继续运行。
- 增加大小写不敏感用户名/邮箱唯一索引前先检测冲突，避免升级时产生难解释的部分迁移。
- 新增 8 个 SQLite 触发器，对用户角色、帖子引用、评论父子关系、采纳状态和活动日志用户引用执行数据库级约束。
- 数据库连接统一开启外键、30 秒超时和 busy timeout；数据库目录/文件在 POSIX 环境尽量收紧到 `0700` / `0600`。

### 3. 评论树与采纳状态

- 父评论必须存在、属于同一帖子且处于可用状态；模型层和数据库触发器双重校验。
- 禁止自引用父评论和跨帖子父评论。
- 评论树批量读取，减少 N+1 查询；深度计算加入循环防护。
- 同一帖子最多只能存在一条有效采纳评论，增加 SQLite partial unique index。
- 采纳必须满足：评论未删除、帖子未删除、游客帖已审核通过、采纳者有效。
- 采纳操作在单事务中清除旧采纳并设置新采纳。
- 删除已采纳评论会原子撤销采纳。
- **修复本轮发现的状态机 bug：已经采纳评论的帖子若随后被删除，或游客帖子由“通过”改为“拒绝”，数据库触发器会立即原子清除采纳状态；不再等到下次重启迁移才修复。**
- 已删除、待审、已拒绝的帖子不能置顶；拒绝/删除会清理不再合法的置顶状态。

### 4. 事务、连接与失败语义

- 评论保存、删除、恢复、采纳/取消采纳等写操作补齐事务回滚和 `finally` 连接关闭。
- 活动日志写入使用事务和 `cursor.lastrowid`。
- 业务操作已经成功后，如果审计日志数据库短暂写入失败，不再向用户返回 500 导致用户重试和重复业务操作；服务器仍记录异常。
- 多处只读查询改为统一 `fetch_one` / `fetch_all`，保证连接释放。
- 管理后台统计改为两个聚合查询，并使用 `finally` 关闭连接，减少查询次数和异常路径连接泄漏。

### 5. 密钥、口令与会话安全

- 首次创建管理员必须设置 `ADMIN_PASSWORD`，不再允许 `admin/admin` 弱默认口令进入数据库。
- 管理员初始化密码最少 12 个字符。
- 显式 `SECRET_KEY` 少于 32 个字符时拒绝启动。
- 未显式设置 `SECRET_KEY` 时，生成高熵随机密钥并持久化到数据目录；密钥文件权限尽量设置为 `0600`。
- 拒绝把符号链接或非普通文件当作密钥文件，降低路径替换风险。
- 无法安全持久化随机密钥时直接报错，不使用每次重启变化的临时密钥继续运行。
- Session/Remember Cookie 设置 HttpOnly、SameSite=Lax；HTTPS 环境可用 `COOKIE_SECURE=true` 强制 Secure。
- Session 生命周期与 remember token 生命周期显式设置。

### 6. 请求、CSRF、XSS 与响应头

- 默认请求体上限 1 MiB，同时限制表单内存和表单字段数量，降低异常大请求资源消耗。
- 32 个 POST 表单静态扫描均包含 CSRF 字段；修改型路由使用 POST + Flask-WTF CSRF。
- `nl2br` 在构造 `Markup` 前先执行 HTML escape，避免通过换行过滤器注入 HTML。
- 未发现 `eval`、`exec`、`os.system`、`pickle`、`render_template_string`、`innerHTML` 等明显高风险动态执行/拼接模式。
- 413 错误页不再使用未经信任的 `Referer` 作为返回链接，固定回站内首页。
- 动态响应增加：`X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`、`Permissions-Policy`、`Cross-Origin-Opener-Policy`、`X-Permitted-Cross-Domain-Policies`。
- 增加基础 CSP：限制 `base-uri`、`object-src`、`frame-ancestors` 与 `form-action`。
- 动态页面默认 `Cache-Control: no-store, private`，降低敏感页面被共享缓存保存的风险。
- 支持 `TRUSTED_HOSTS` 配置限制 Host。

### 7. 游客审核与内容可见性

- 待审核和已拒绝游客帖只对允许的管理角色可见/管理。
- 游客功能关闭后，已存在游客会话不再继续使用受限能力。
- 游客发帖自动账号创建失败时增加防御性处理，避免 `None.is_banned` 类异常。
- 待审/拒绝/删除帖子在路由层与数据库层都不能进入置顶/采纳等不合法状态。

### 8. 部署加固

- `requirements.txt` 统一精确锁定 13 个直接/运行时依赖版本，包含 Gunicorn。
- Docker 以非 root 用户运行，去除不必要构建工具。
- Compose 强制首次部署提供 `ADMIN_PASSWORD`。
- 容器根文件系统设置为只读，`/tmp` 使用独立 tmpfs。
- `no-new-privileges`、`cap_drop: ALL`、PID 上限、CPU/内存约束与日志轮转已配置。
- 入口脚本使用 `umask 077`，并验证 Gunicorn workers、threads、log level 环境变量，避免无效值直接进入启动参数。
- `.dockerignore` 排除测试、审计报告、备份文件和内部工作目录，减少生产镜像暴露面。
- `/healthz` 会实际探测 SQLite；数据库不可用时返回 503。

## 实际验证结果

| 验证项 | 结果 | 说明 |
|---|---|---|
| Python 全量语法/字节码编译 | 通过 | `py_compile` / `compileall` |
| Jinja2 模板独立语法编译 | 通过 | 19/19；为项目自定义过滤器提供等价占位注册 |
| POST 表单 CSRF 静态检查 | 通过 | 32/32 |
| requirements 精确版本检查 | 通过 | 13/13 使用 `==` |
| Docker Compose YAML 解析 | 通过 | 同时断言只读根文件系统/PID 限制等配置 |
| `docker-entrypoint.sh` Shell 语法 | 通过 | `sh -n` |
| SECRET_KEY 持久化烟雾测试 | 通过 | 重载稳定、文件权限 `0600` |
| 弱显式 SECRET_KEY 拒绝 | 通过 | 小于 32 字符触发启动异常 |
| SQLite 模型/触发器烟雾测试 | 通过 | 跨帖父评论、待审置顶/采纳、系统角色、隐藏帖采纳联动等 |
| 旧数据库迁移专项测试 | 通过 | 使用旧结构建库后连续执行迁移，数据保留且新约束生效 |
| SQLite 完整性检查 | 通过 | `PRAGMA integrity_check` 返回 `ok` |
| 完整 Flask `unittest` / `pytest` | 通过 | 47/47 全部通过（`python -m unittest discover -s tests -q`、`python -m pytest -q`） |
| 全路由动态探测 | 通过 | 普通用户 / 游客 / 管理员 / 子管理员所有路由均无 500，未知路由 404 |
| 真实 Gunicorn 启动烟雾测试 | 通过 | `/healthz` 200、`/login` 200、匿名 `/` 302、未知 URL 404、静态资源 200、数据库与密钥文件权限 `0600` |
| 旧数据库迁移探测 | 通过 | 缺列旧库、空邮箱旧库迁移成功；孤立数据与双角色数据按设计拒绝启动 |

完整测试文件已经扩展为 **47 个测试方法**。在正常安装依赖的 Python 环境执行：

```bash
pip install -r requirements.txt
export ADMIN_PASSWORD='至少12位的强管理员密码'
python -m unittest discover -s tests -v
```

## 残余风险 / 建议

以下项目不是本轮发现的直接可利用逻辑 bug，但生产环境仍建议继续处理：

1. **登录速率限制**：应用本身尚未集成登录/注册的 IP 或账号级 rate limit。公网部署应在反向代理/WAF 层或应用层增加限速与失败退避。
2. **前端外部资源与严格 CSP**：当前页面仍使用 Tailwind CDN、Google Fonts，并存在内联 JavaScript。为了不在无浏览器/构建链的环境下破坏 UI，本轮只启用了不会影响现有页面的 CSP 子集。高安全部署建议将前端依赖本地化、把内联脚本迁移到静态 JS，再收紧 `script-src` / `style-src`。
3. **HSTS**：只有确认全站长期 HTTPS 后才适合启用。建议由 TLS 终止的反向代理设置 HSTS，而不是在本地 HTTP 开发环境强制。
4. **SQLite 部署边界**：当前事务和 busy timeout 已强化，但 SQLite 仍更适合单实例/中低写并发。若未来需要多实例水平扩展、高写并发或高可用，应迁移到服务器型数据库并设计正式迁移工具。
5. **浏览器端 E2E 验证**：47 个 Flask 回归测试与 Gunicorn 烟雾测试已通过，但仍建议在 CI 或实际部署环境补一次真实浏览器端流程/E2E 检查（登录、发帖、评论、审核、采纳、封禁等完整交互链路）。

## 推荐启动方式

### Docker Compose

```bash
export ADMIN_PASSWORD='至少12位的强管理员密码'
# HTTPS 反向代理环境：
# export COOKIE_SECURE=true
# export TRUSTED_HOSTS=example.com,www.example.com

docker compose up -d --build
```

### 本地 Python

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export ADMIN_PASSWORD='至少12位的强管理员密码'
python -m unittest discover -s tests -v
python app.py
```

生产环境建议显式提供长度不少于 32 字符的 `SECRET_KEY`；若未提供，应用/容器会在数据目录安全生成并持久化随机密钥。
