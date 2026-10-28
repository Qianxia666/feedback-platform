# 反馈平台

基于 Flask + SQLite 的反馈收集与管理平台，支持注册用户与游客反馈、评论讨论、游客内容审核、软删除、评论采纳、置顶和多级管理员权限。

## 主要功能

- 用户注册、登录、个人资料与密码管理
- 反馈发布、评论、回复、删除与恢复
- 评论采纳/取消采纳
- 管理员 / 子管理员 / 普通用户 / 游客权限分离
- 游客反馈审核、通过与拒绝
- 反馈置顶、用户封禁、平台设置、活动日志
- SQLite 数据库备份导出
- 健康检查 `/healthz`

## 技术栈

- Python / Flask
- SQLite
- Flask-Login / Flask-WTF / WTForms
- Jinja2 + Tailwind CSS + JavaScript
- Gunicorn
- Docker / Docker Compose

## Docker Compose 部署（推荐）

环境要求：Docker 20.10+、Docker Compose 2.x。

```bash
# 首次初始化必须提供管理员密码，至少 12 个字符
export ADMIN_PASSWORD='请替换为至少12位的强密码'

# HTTPS 反向代理部署时建议开启
# export COOKIE_SECURE=true

# 域名固定时建议限制 Host
# export TRUSTED_HOSTS=example.com,www.example.com

# 可选：显式提供至少 32 字符的会话密钥；未设置时会在数据卷安全生成
# export SECRET_KEY='至少32字符的高熵随机字符串'

docker compose up -d --build
docker compose ps
```

访问地址默认为 `http://localhost:5000`。首次初始化创建管理员用户名 `admin`，密码为 `ADMIN_PASSWORD`。未提供管理员密码或密码不足 12 个字符时会拒绝初始化。

容器使用非 root 用户、只读根文件系统、独立 `/tmp` tmpfs、能力集清空、`no-new-privileges` 和 PID/资源限制。SQLite 数据与自动生成的密钥保存在持久化数据卷中。

## 本地运行

推荐 Python 3.12（Docker 镜像使用 Python 3.12）。

```bash
python -m venv .venv
. .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export ADMIN_PASSWORD='请替换为至少12位的强密码'
# 可选：开发调试
# export FLASK_DEBUG=1

python app.py
```

默认地址：`http://localhost:5000`。

## 运行测试

```bash
python -m unittest discover -s tests -v
```

当前回归测试覆盖权限边界、游客审核、评论嵌套、数据库触发器、旧库迁移、密码/会话失效、CSRF、XSS 过滤、开放重定向、备份导出和安全响应头等场景。

## 关键环境变量

| 变量 | 用途 | 默认/要求 |
|---|---|---|
| `ADMIN_PASSWORD` | 首次初始化 `admin` 密码 | 必填，至少 12 字符 |
| `SECRET_KEY` | Flask 会话签名密钥 | 可选；显式设置时至少 32 字符；未设置时持久化生成 |
| `COOKIE_SECURE` | Cookie Secure 标记 | `false`；HTTPS 生产环境建议 `true` |
| `TRUSTED_HOSTS` | 允许的 Host，逗号分隔 | 未设置则不额外限制 |
| `MAX_CONTENT_LENGTH` | 最大请求体字节数 | 默认 1 MiB |
| `DB_DIR` | SQLite/密钥数据目录 | 默认项目根目录；容器为 `/app/data` |
| `FLASK_DEBUG` | 本地调试模式 | 默认关闭 |

## 安全设计摘要

- CSRF 保护覆盖修改型表单/路由。
- 登录后 `next` 仅允许站内跳转。
- 密码修改会使旧会话和 remember token 失效。
- 系统账号与管理员角色有模型层和 SQLite 触发器双重约束。
- 子管理员不能横向管理管理员或其他子管理员。
- 评论父子关系必须在同一帖子内；同一帖子最多一条有效采纳评论。
- 删除/拒绝帖子会原子清理不再合法的置顶/采纳状态。
- 动态页面启用基础 CSP、点击劫持/类型嗅探/Referrer/Permissions 等安全响应头。
- 默认限制请求体、表单内存和表单字段数量。
- 数据库目录/文件与自动生成的密钥文件会尽量使用最小权限。

公网部署仍建议在 HTTPS 反向代理或 WAF 层增加登录速率限制、HSTS、访问日志和备份策略。若需要严格 CSP，建议将 Tailwind/字体本地化并移除内联 JavaScript。

## 项目结构

```text
feedback-platform/
├── app.py
├── config.py
├── models.py
├── forms.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── AUDIT_REPORT.md
├── static/
├── templates/
└── tests/
```

## 权限角色

| 角色 | 权限概览 |
|---|---|
| 普通用户 | 发布反馈、评论，管理自己的内容 |
| 子管理员 | 管理普通用户及内容，但不能管理管理员/其他子管理员 |
| 管理员 | 用户、权限、系统设置与内容管理 |
| 游客 | 无需注册，可按平台设置发布反馈/评论；反馈需审核 |

更完整的第二轮代码审计、修复项、实际验证结果与残余风险见 `AUDIT_REPORT.md`。
