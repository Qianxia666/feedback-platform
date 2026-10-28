# 反馈平台

一个基于 Flask + SQLite 的轻量反馈收集与讨论平台。注册用户和游客都可以提交反馈、参与评论；管理员可以审核游客内容、置顶反馈、封禁用户、调整平台设置，并一键导出数据库。

单容器即可运行，不需要额外的数据库服务，适合小团队内部的意见收集、产品建议、需求反馈等场景。

## 目录

- [功能亮点](#功能亮点)
- [快速开始](#快速开始)
- [首次使用](#首次使用)
- [角色与权限](#角色与权限)
- [配置项](#配置项)
- [常用运维](#常用运维)
- [项目结构](#项目结构)
- [运行测试](#运行测试)
- [安全说明](#安全说明)
- [常见问题](#常见问题)
- [许可证](#许可证)

## 功能亮点

**反馈与讨论**

- 发布反馈（标题 3–100 字，内容 10–1000 字），列表分页展示
- 多级评论与回复（最多 5 层嵌套，单条评论 2–500 字）
- 评论采纳 / 取消采纳，每个反馈最多保留一条有效采纳评论
- 帖子与评论软删除、可恢复，管理员可查看回收站
- 反馈置顶

**账号与权限**

- 注册、登录、记住我、修改资料与密码
- 密码修改后，旧会话和 remember token 自动失效
- 游客免注册进入（后台可开关），游客发布的反馈需审核
- 管理员 / 子管理员 / 普通用户 / 游客四级权限
- 封禁 / 解封用户，提升 / 降级角色

**管理后台**

- 仪表盘：用户与反馈统计、待审核数量、近期活动日志
- 游客反馈审核（通过 / 拒绝）
- 平台设置：平台名称、游客访问开关、游客评论开关、时区
- 数据库备份导出

**安全与运维**

- 全站 CSRF 保护、登录跳转防止开放重定向、输出转义防 XSS
- 安全响应头：CSP、X-Frame-Options、nosniff、Referrer-Policy 等
- 角色约束由模型层与 SQLite 触发器双重保障
- `/healthz` 健康检查端点
- 容器以非 root 运行、只读根文件系统、清空能力集、限制资源

## 快速开始

### 方式一：Docker Compose（推荐）

环境要求：Docker 20.10+、Docker Compose 2.x。

```bash
# 1. 设置管理员初始密码（至少 12 位，仅在首次初始化时使用）
export ADMIN_PASSWORD='请替换为至少12位的强密码'

# 2. 构建并启动
docker compose up -d --build

# 3. 查看状态，健康检查为 healthy 即启动完成
docker compose ps
```

浏览器打开 `http://localhost:5000`，使用用户名 `admin` 和刚才设置的 `ADMIN_PASSWORD` 登录。

数据保存在名为 `feedback-data` 的 Docker 卷中（容器内 `/app/data`），包括 SQLite 数据库和自动生成的会话密钥。删除容器不会丢数据，但 `docker compose down -v` 会删除数据卷，请谨慎操作。

生产环境通过 HTTPS 访问时，建议补充以下配置：

```bash
export COOKIE_SECURE=true
export TRUSTED_HOSTS=example.com,www.example.com

# 可选：显式指定至少 32 字符的会话密钥（未设置时会在数据卷中自动生成）
export SECRET_KEY='至少32字符的高熵随机字符串'

docker compose up -d
```

### 方式二：本地运行

推荐 Python 3.12（与 Docker 镜像保持一致）。

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt

export ADMIN_PASSWORD='请替换为至少12位的强密码'
# Windows PowerShell: $env:ADMIN_PASSWORD="请替换为至少12位的强密码"

python app.py
```

默认访问地址为 `http://127.0.0.1:5000`，数据库文件生成在项目根目录的 `feedback.db`。需要调试时可设置 `FLASK_DEBUG=1`。

## 首次使用

1. **登录管理员**：用户名 `admin`，密码为 `ADMIN_PASSWORD`。管理员账号只在数据库首次初始化时创建，之后再修改环境变量不会改变密码。
2. **调整平台设置**：进入「管理面板 → 系统设置」，设置平台名称、是否允许游客访问、是否允许游客评论、系统时区。
3. **管理用户**：在「管理面板 → 用户管理」中查看用户，可将普通用户提升为子管理员或管理员。
4. **体验游客流程**：登录页点击「游客登录」即可免注册发帖；游客反馈会进入待审核列表，管理员通过后才会公开展示。
5. **注册普通用户**：退出登录后注册新账号即可（用户名 3–20 位，密码至少 8 位）。

## 角色与权限

| 角色 | 可以做什么 | 限制 |
|---|---|---|
| 游客 | 免注册浏览、发布反馈与评论（需后台开启） | 发布的反馈需审核；受游客开关控制 |
| 普通用户 | 发布反馈、评论回复、管理自己的内容 | 无法进入管理后台 |
| 子管理员 | 管理普通用户与内容、审核、置顶、封禁普通用户 | 不能管理管理员或其他子管理员，不能修改系统设置 |
| 管理员 | 全部内容与用户管理、系统设置、数据库导出 | — |

补充说明：`admin` 与 `tourist` 是系统保留用户名，不可注册；游客账号不能被授予管理权限。

## 配置项

| 变量 | 说明 | 默认值 / 要求 |
|---|---|---|
| `ADMIN_PASSWORD` | 首次初始化时 `admin` 的密码 | 必填，至少 12 字符，否则拒绝初始化 |
| `SECRET_KEY` | Flask 会话签名密钥 | 可选；显式设置时至少 32 字符 |
| `SECRET_KEY_FILE` | 自动生成密钥的保存路径 | 默认 `DB_DIR/.secret_key`，权限 0600 |
| `COOKIE_SECURE` | Cookie 是否只通过 HTTPS 发送 | `false`；HTTPS 环境建议 `true` |
| `TRUSTED_HOSTS` | 允许的 Host 列表，逗号分隔 | 空，不做额外限制 |
| `MAX_CONTENT_LENGTH` | 请求体大小上限（字节） | 1048576（1 MiB） |
| `MAX_FORM_MEMORY_SIZE` | 表单内存上限（字节） | 262144（256 KiB） |
| `MAX_FORM_PARTS` | 表单字段与文件数量上限 | 64 |
| `DB_DIR` | 数据库与密钥存放目录 | 项目根目录；容器内为 `/app/data` |
| `FLASK_HOST` | 本地运行时监听地址 | `127.0.0.1`；容器内为 `0.0.0.0` |
| `PORT` | 本地运行时监听端口 | `5000` |
| `FLASK_DEBUG` | 本地调试模式 | 关闭 |
| `WORKERS` | Gunicorn 工作进程数（容器） | 2，范围 1–32 |
| `THREADS` | 每个进程的线程数（容器） | 2，范围 1–64 |
| `LOG_LEVEL` | Gunicorn 日志级别 | `info` |

> 提示：更换 `SECRET_KEY` 会让所有已登录会话失效。多实例部署请显式设置相同的 `SECRET_KEY`，并共享同一个数据卷。

## 常用运维

```bash
docker compose logs -f                        # 实时查看日志
docker compose restart                        # 重启服务
docker compose up -d --build                  # 更新代码后重新构建
docker compose down                           # 停止服务（保留数据卷）

curl -fsS http://localhost:5000/healthz       # 健康检查，正常返回 {"status":"ok"}
```

**备份数据**：管理员可在「系统设置」页点击「导出数据库」下载完整的 SQLite 文件；也可以直接备份 `feedback-data` 卷（或宿主机上的 `/app/data` 目录）。

## 项目结构

```text
.
├── app.py                 # 应用工厂、路由、请求钩子与安全响应头
├── config.py              # 配置项、环境变量解析与会话密钥管理
├── models.py              # SQLite 建表与迁移、数据模型、业务约束
├── forms.py               # WTForms 表单与校验规则
├── templates/             # Jinja2 模板（含 admin/ 后台页面与错误页）
├── static/css/style.css   # 自定义样式
├── tests/test_app.py      # 回归测试
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh   # 容器启动脚本：校验参数、初始化数据库、启动 Gunicorn
├── AUDIT_REPORT.md        # 代码审计报告：修复项、验证结果与残余风险
├── requirements.txt
└── LICENSE                # GPL-3.0
```

技术栈：Python 3.12、Flask 3、Flask-Login、Flask-WTF / WTForms、SQLite（WAL 模式）、Jinja2、Tailwind CSS（CDN）、Gunicorn、Docker。

> 页面通过 CDN 加载 Tailwind CSS 和 Inter 字体。完全离线部署时需要将这两个资源本地化，并相应调整 CSP 配置。

## 运行测试

```bash
python -m unittest discover -s tests -v
```

测试使用临时目录和临时数据库，不会影响本地数据。当前覆盖权限边界、游客审核、评论嵌套、数据库触发器、旧库迁移、密码与会话失效、CSRF、XSS 过滤、开放重定向、备份导出、安全响应头等场景。

## 安全说明

已经实现的安全措施：

- 修改型表单与路由均启用 CSRF 保护
- 登录后的 `next` 参数仅允许站内跳转
- 密码修改会使旧会话和 remember token 失效
- 系统账号与管理员角色受模型层和 SQLite 触发器双重约束
- 子管理员不能横向管理管理员或其他子管理员
- 评论父子关系必须属于同一帖子；每个帖子最多一条有效采纳评论
- 删除或拒绝帖子时，原子清理不再合法的置顶 / 采纳状态
- 动态页面启用基础 CSP 及点击劫持、类型嗅探、Referrer、Permissions 等安全响应头
- 默认限制请求体、表单内存和表单字段数量
- 数据库目录、文件与自动生成的密钥文件尽量使用最小权限

公网部署时仍建议：

- 通过 HTTPS 反向代理或 WAF 提供访问，开启 HSTS 和访问日志
- 在网关层增加登录速率限制
- 定期备份数据卷，并妥善保管 `SECRET_KEY`
- 如需严格 CSP，请本地化 Tailwind 与字体资源，并移除内联 JavaScript

更完整的审计结论、修复项与残余风险见 [`AUDIT_REPORT.md`](AUDIT_REPORT.md)。

## 常见问题

**启动时提示需要 `ADMIN_PASSWORD`？**

首次初始化必须提供该变量，且长度至少 12 个字符。Docker Compose 中未设置会直接报错退出。

**忘了管理员密码怎么办？**

平台没有内置找回入口。其他用户可由管理员在「用户管理 → 编辑用户」中重置密码；如果管理员本人密码丢失，只能通过直接修改数据库或删除数据卷重新初始化（会丢失全部数据）。建议初始化后立即妥善保存密码。

**5000 端口被占用？**

修改 `docker-compose.yml` 中的端口映射，例如将 `"5000:5000"` 改为 `"8080:5000"`，然后访问 `http://localhost:8080`。

**登录页看不到「游客登录」按钮？**

说明游客访问已被关闭。用管理员账号登录后，在「系统设置」中开启「允许游客访问」。

**修改密码后为什么被登出了？**

这是安全设计：密码修改会让旧会话和 remember token 失效，需要重新登录。

**数据保存在哪里？如何迁移？**

容器内路径为 `/app/data/feedback.db`，对应 Docker 卷 `feedback-data`。迁移时整体复制该目录，并保持相同的 `SECRET_KEY`，否则用户需要重新登录。

**页面样式或字体加载失败？**

页面依赖 `cdn.tailwindcss.com` 与 `fonts.googleapis.com`，请确认网络可访问；离线环境需本地化相关资源。

## 许可证

本项目采用 GPL-3.0 许可证，详见 [`LICENSE`](LICENSE)。
