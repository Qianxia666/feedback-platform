# 反馈平台

一个基于 Flask + SQLite 的轻量反馈收集与讨论平台。注册用户和游客都可以提交反馈、参与评论；管理员可以审核游客内容、置顶反馈、封禁用户、调整平台设置并导出数据库。

单容器即可运行，不需要额外的数据库服务，适合小团队内部的意见收集、产品建议、需求反馈等场景。

> 第一次部署？直接照着 [方式一](#方式一docker-compose-部署推荐) 的 8 个步骤操作即可，每一步都说明了要输入什么、看到什么算成功。遇到问题可先查 [常见问题](#常见问题)。

## 目录

- [功能亮点](#功能亮点)
- [部署前必读](#部署前必读)
- [方式一：Docker Compose 部署](#方式一docker-compose-部署推荐)
- [方式二：本地运行](#方式二本地运行)
- [部署后检查清单](#部署后检查清单)
- [首次使用](#首次使用)
- [角色与权限](#角色与权限)
- [配置项](#配置项)
- [日常运维](#日常运维)
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
- 帖子与评论软删除、可恢复，管理员可查看已删除内容
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

## 部署前必读

### 先认识几个词

| 名词 | 通俗解释 |
|---|---|
| 终端 | 用来输入命令的窗口。Windows 叫 PowerShell，macOS 叫「终端」，Linux 叫 Shell |
| 项目目录 | 下载项目后，包含 `docker-compose.yml` 的那个文件夹。后续命令都要在这里执行 |
| 镜像 | 打包好的运行环境，可以理解为「安装包模板」 |
| 容器 | 镜像启动后的运行实例。本项目的容器名是 `feedback-platform` |
| 数据卷 | Docker 管理的持久化磁盘。本项目使用 `feedback-data`，容器内对应 `/app/data` |
| 端口 | 网址里 `:5000` 这样的数字。本机访问就是 `http://localhost:5000` |
| 环境变量 | 启动前传给程序的配置，例如管理员初始密码 `ADMIN_PASSWORD` |

### 选择部署方式

| 你的情况 | 推荐方式 | 需要安装 |
|---|---|---|
| 只想在本机试用、看看功能 | [方式二：本地运行](#方式二本地运行) | Python 3.12 |
| 给团队长期使用，局域网访问 | [方式一：Docker](#方式一docker-compose-部署推荐) | Docker |
| 放到公网，通过域名访问 | 方式一 + HTTPS 反向代理 | Docker、域名 |

### 开始前准备

- 一台电脑或服务器（Windows 10/11、macOS、主流 Linux 均可）
- 首次安装依赖时需要网络，能访问 GitHub、Docker Hub 或 PyPI
- 一个至少 12 位的管理员密码，建议包含字母、数字和符号
- 大约 10–20 分钟
- 如果要放到公网：一台有公网 IP 的服务器、一个已解析的域名（可选）

> 下文命令都在终端中执行。Windows 在开始菜单搜索 PowerShell；macOS 在启动台搜索「终端」；Linux 常用 `Ctrl + Alt + T`。
> 以 `#` 开头的是注释，不需要输入。

## 方式一：Docker Compose 部署（推荐）

适合长期使用，也适合完全没部署过 Web 应用的新手。完成后会得到一个自动启动、数据持久化、带健康检查的服务。

### 第 1 步：安装并确认 Docker

先检查电脑上是否已经有 Docker：

```bash
docker --version
docker compose version
```

两条命令都能输出版本号即可（版本号不必完全一致）。

如果没有安装：

- **Windows / macOS**：安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)。Windows 安装时按提示启用 WSL2，安装完成后启动 Docker Desktop，等状态显示为 Engine running。
- **Linux**：按 [Docker 官方文档](https://docs.docker.com/engine/install/) 安装 Docker Engine 和 Compose 插件。

安装完成后关闭终端再重新打开，然后再次执行上面的检查命令。

> `docker compose`（中间有空格）是 Compose v2 的写法。若提示 `docker: 'compose' is not a docker command`，说明版本过旧，请升级 Docker Desktop 或 Compose 插件。旧版的 `docker-compose`（带连字符）不在本文命令范围内。

### 第 2 步：下载项目

有 Git 时，在终端执行：

```bash
git clone https://github.com/Qianxia666/feedback-platform.git
cd feedback-platform
```

没有 Git 时：

1. 打开项目主页，点击绿色的 **Code** 按钮，选择 **Download ZIP**
2. 解压到一个你找得到的目录
3. 在该目录中打开终端
   - Windows：在文件夹空白处按住 `Shift` 再点右键，选择「在此处打开 PowerShell 窗口」或「在终端中打开」
   - macOS：输入 `cd `（注意后面有空格），把文件夹拖进终端窗口，按回车
4. 解压后的文件夹名可能是 `feedback-platform-main`，进入该文件夹即可

确认当前目录是否正确：

```bash
ls        # Windows 使用 dir
```

应该能看到 `docker-compose.yml`、`Dockerfile`、`app.py` 等文件。**如果看不到，请先不要继续，确认终端所在目录是否正确。**

### 第 3 步：配置管理员密码（只需做一次）

首次启动时，程序会用 `ADMIN_PASSWORD` 创建管理员账号 `admin`。这个密码必须至少 12 个字符，否则程序会拒绝初始化。

推荐在项目根目录（和 `docker-compose.yml` 同一层）新建一个名为 `.env` 的文件，内容如下：

```ini
ADMIN_PASSWORD='ReplaceWithYourStrongPass123!'
```

请把引号中的内容换成你自己的强密码。几点说明：

- 文件名必须正好是 `.env`。用记事本保存时，保存类型选「所有文件」，编码选 UTF-8，避免变成 `.env.txt`
- Docker Compose 会自动读取这个文件，之后执行任何 `docker compose` 命令都不需要再手动设置密码
- `.env` 已被 `.gitignore` 忽略，不会被提交；也不要把它发给别人
- 建议密码只使用英文、数字和常见符号，避免空格、引号和 `$`，以免被配置文件解析
- macOS / Linux 可以顺便收紧权限：`chmod 600 .env`

如果你只想临时设置一次，也可以在当前终端执行：

```bash
# macOS / Linux
export ADMIN_PASSWORD='ReplaceWithYourStrongPass123!'
```

```powershell
# Windows PowerShell
$env:ADMIN_PASSWORD = "ReplaceWithYourStrongPass123!"
```

这种方式只对当前终端窗口有效，关闭窗口后就失效。因此长期使用更推荐 `.env`。

> `ADMIN_PASSWORD` 只在首次初始化时生效。数据库已经存在管理员后，再改这个值不会改变密码，需要登录后在页面中修改。

### 第 4 步：启动

在项目目录执行：

```bash
docker compose up -d --build
```

参数含义：

- `--build`：根据 `Dockerfile` 构建镜像
- `-d`：在后台运行，不占用当前终端

第一次启动需要下载 Python 镜像并安装依赖，可能持续几分钟，属于正常现象。结束时看到类似下面的输出就表示已启动：

```text
Container feedback-platform  Started
```

如果这里报错，先跳到 [常见问题 → 部署相关](#部署相关)。

### 第 5 步：确认启动成功

```bash
docker compose ps
```

正常情况下 `STATUS` 一列会显示 `Up ... (healthy)`。刚启动的前 30–60 秒可能显示 `(health: starting)`，等待一会儿再执行一次即可。

如果状态是 `Restarting`、`Exited` 或 `unhealthy`，查看日志定位原因：

```bash
docker compose logs --tail=80
```

启动成功时，日志中通常能看到：

```text
Starting feedback platform with 2 workers and 2 threads
Running in production mode
Listening at: http://0.0.0.0:5000
```

也可以用浏览器访问健康检查地址 `http://localhost:5000/healthz`，看到 `{"status":"ok"}` 即表示服务正常。

### 第 6 步：打开页面

- **就在当前电脑访问**：打开 `http://localhost:5000`
- **在同一局域网的其他设备访问**：打开 `http://服务器或电脑的IP:5000`
  - Windows 用 `ipconfig` 查看「IPv4 地址」
  - macOS / Linux 用 `ip addr`、`ifconfig` 或 `hostname -I`
  - 云服务器使用控制台里的公网 IP
- **访问不了时依次检查**
  - 不要用 `localhost` 从另一台设备访问，必须用 IP
  - 云服务器安全组是否放行了 TCP 5000
  - Linux 防火墙：`sudo ufw allow 5000/tcp`
  - Windows 防火墙弹窗是否点了允许

> 团队内网使用到这里就可以开始了。要放到公网，请继续第 8 步配置 HTTPS，不要直接用 HTTP 暴露登录密码。

### 第 7 步：登录并完成初始化

1. 使用用户名 `admin` 和你在第 3 步设置的密码登录
2. 点击右上角用户名进入个人主页，再点「修改个人信息」修改密码（需要输入当前密码，修改后会自动退出并要求重新登录）
3. 点击「控制台」进入管理后台
4. 打开「系统设置」，设置平台名称、时区和游客策略
5. 按需在「用户管理」中创建或调整用户角色

更详细的页面位置见 [首次使用](#首次使用)。

### 第 8 步（可选）：配置 HTTPS 与域名

只在内网使用可以跳过。公网部署时，建议用反向代理提供 HTTPS，避免密码和会话明文传输。

1. 把域名解析到服务器 IP，并在安全组放行 80 / 443 端口
2. 安装反向代理，例如 [Caddy](https://caddyserver.com/docs/install)，配置示例：

```caddyfile
example.com {
    reverse_proxy 127.0.0.1:5000
}
```

把 `example.com` 换成你的域名。Caddy 会自动申请并续期 HTTPS 证书。

3. 修改 `docker-compose.yml`，让 5000 端口只监听本机，不直接暴露到公网：

```yaml
ports:
  - "127.0.0.1:5000:5000"
```

4. 在 `.env` 中补充：

```ini
COOKIE_SECURE=true
TRUSTED_HOSTS=example.com,127.0.0.1
```

如果同时使用 `www` 域名，写成 `TRUSTED_HOSTS=example.com,www.example.com,127.0.0.1`。

必须保留 `127.0.0.1`：容器自带的健康检查会访问 `http://127.0.0.1:5000/healthz`，如果 Host 不被信任，健康检查会失败并显示 `unhealthy`。

5. 应用配置：

```bash
docker compose up -d
```

6. 在防火墙 / 安全组中关闭 5000 端口，只保留 80 和 443

> 开启 `COOKIE_SECURE=true` 后，必须通过 HTTPS 访问，否则无法登录。等 HTTPS 正常后再开启。
> 使用 Nginx 的用户，把请求反向代理到 `http://127.0.0.1:5000` 即可，同样需要设置 `COOKIE_SECURE` 和 `TRUSTED_HOSTS`。

## 方式二：本地运行

适合在自己电脑上快速体验或二次开发。**不建议直接用于公网生产环境**，因为这里启动的是 Flask 开发服务器。

### 第 1 步：安装 Python

推荐 Python 3.12（与 Docker 镜像一致）。先检查：

```bash
python3 --version    # Windows 使用 python --version
```

没有安装或版本过低时：

- Windows：从 [python.org](https://www.python.org/downloads/) 下载安装，安装时勾选 **Add python.exe to PATH**
- macOS：从 python.org 下载安装包，或使用 Homebrew
- Linux：使用发行版的包管理器安装 Python 3 和 `python3-venv`

### 第 2 步：下载项目

与方式一第 2 步相同：`git clone` 或下载 ZIP，然后进入项目目录。

### 第 3 步：创建并激活虚拟环境

虚拟环境可以避免污染系统 Python，且方便以后删除。

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

成功后，命令行提示符前会出现 `(.venv)`。**每次新开终端都需要重新激活虚拟环境。**

如果 PowerShell 提示「因为在此系统上禁止运行脚本」，先执行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

再重新执行激活命令。该设置只对当前窗口生效。

### 第 4 步：安装依赖

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

国内网络较慢时，可以临时使用镜像：

```bash
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第 5 步：设置管理员密码并启动

macOS / Linux：

```bash
export ADMIN_PASSWORD='ReplaceWithYourStrongPass123!'
python app.py
```

Windows PowerShell：

```powershell
$env:ADMIN_PASSWORD = "ReplaceWithYourStrongPass123!"
python app.py
```

看到类似输出后，打开 `http://127.0.0.1:5000`：

```text
Running on http://127.0.0.1:5000
```

> 本地运行不会读取 `.env` 文件，必须在终端中用 `export` / `$env:` 设置。
> 数据库首次初始化后管理员已存在，之后再启动可以省略 `ADMIN_PASSWORD`。

### 第 6 步：停止与再次启动

在终端按 `Ctrl + C` 停止。下次启动时：

```bash
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
python app.py
```

数据保存在项目根目录的 `feedback.db`（以及 `feedback.db-wal`、`feedback.db-shm`）和 `.secret_key` 中。**删除这些文件会丢失全部数据并重新初始化**，下次启动又需要 `ADMIN_PASSWORD`。

如果只是想让局域网访问，可临时设置 `FLASK_HOST=0.0.0.0`，但请只在可信网络使用，不要暴露到公网。

## 部署后检查清单

部署完成后，建议逐项确认：

- [ ] `docker compose ps` 显示 `Up ... (healthy)`，或本地运行页面可打开
- [ ] 首页能正常加载，样式完整
- [ ] 能用 `admin` 登录
- [ ] 已修改并妥善记录管理员密码
- [ ] 平台名称、时区已设置
- [ ] 已决定是否允许游客访问和评论
- [ ] 能注册普通用户并正常登录（可选）
- [ ] 已成功导出一份数据库备份
- [ ] 公网部署时：HTTPS 可用、`COOKIE_SECURE=true`、`TRUSTED_HOSTS` 正确、5000 端口未直接暴露

## 首次使用

### 页面在哪里

| 想做什么 | 入口 |
|---|---|
| 浏览反馈、查看详情与评论 | 首页「反馈广场」，点击反馈卡片 |
| 发布反馈 | 首页右下角的蓝色圆形 `+` 按钮 |
| 修改资料或密码 | 右上角用户名 → 个人主页 → 「修改个人信息」 |
| 进入管理后台 | 右上角用户名 → 个人主页 → 「控制台」 |
| 审核游客反馈 | 控制台 → 「待审核反馈」 |
| 管理用户、角色、封禁 | 控制台 → 「用户管理」 |
| 平台设置、导出数据库 | 控制台 → 「系统设置」 |
| 以游客身份进入 | 登录页下方的「游客登录」按钮 |

### 建议的初始化顺序

1. 登录管理员并修改密码
2. 在「系统设置」中填写平台名称、选择时区
3. 决定游客策略：是否允许游客访问、是否允许游客评论
4. 在「用户管理」中创建团队账号，或将普通用户提升为子管理员
5. 导出一份数据库备份，并保存到安全位置

## 角色与权限

| 角色 | 可以做什么 | 限制 |
|---|---|---|
| 游客 | 免注册浏览、发布反馈与评论（需后台开启） | 发布的反馈需审核；受游客开关控制 |
| 普通用户 | 发布反馈、评论回复、管理自己的内容 | 无法进入管理后台 |
| 子管理员 | 管理普通用户与内容、审核、置顶、封禁普通用户 | 不能管理管理员或其他子管理员，不能修改系统设置 |
| 管理员 | 全部内容与用户管理、系统设置、数据库导出 | — |

补充说明：`admin` 与 `tourist` 是系统保留用户名，不可注册；游客账号不能被授予管理权限。

## 配置项

修改配置后，Docker 部署需要执行 `docker compose up -d` 让容器重新创建；本地运行需要重新设置环境变量并重启。

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

### `.env` 示例

Docker Compose 会自动读取项目目录下的 `.env`：

```ini
# 管理员初始密码，只在首次初始化时生效
ADMIN_PASSWORD='ReplaceWithYourStrongPass123!'

# 通过 HTTPS 访问时改为 true
COOKIE_SECURE=false

# 固定域名访问时填写；保留 127.0.0.1 供容器健康检查
# 例如 example.com,www.example.com,127.0.0.1
TRUSTED_HOSTS=

# 可选：显式指定至少 32 字符的会话密钥
# SECRET_KEY='ReplaceWithA32CharacterRandomString'
```

> `.env` 只对 Docker Compose 生效。本地运行请在终端中使用 `export` 或 `$env:`。
> 更换 `SECRET_KEY` 会让所有已登录会话失效。多实例部署请显式设置相同的值，并共享同一个数据卷。

## 日常运维

| 操作 | 命令 |
|---|---|
| 查看运行状态 | `docker compose ps` |
| 实时查看日志 | `docker compose logs -f --tail=100` |
| 重启 | `docker compose restart` |
| 停止（保留容器和数据） | `docker compose stop` |
| 再次启动 | `docker compose start` |
| 停止并删除容器（保留数据卷） | `docker compose down` |
| 更新版本并重建 | `git pull && docker compose up -d --build` |
| 删除容器和全部数据（危险） | `docker compose down -v` |

**日志**：启动失败、页面报错、健康检查不通过时，先看 `docker compose logs --tail=80`。

**升级**：`git pull && docker compose up -d --build` 会保留 `.env` 和数据卷。用 ZIP 下载的用户可以重新下载并覆盖项目文件，但要保留原来的 `.env`。不要执行 `down -v`。

**备份**：

- 管理员在「系统设置」页点击「导出数据库」，可下载完整的 SQLite 文件，适合日常备份
- Linux / macOS 还可以直接备份数据卷：

```bash
docker run --rm -v feedback-data:/data -v "$PWD":/backup alpine tar czf /backup/feedback-data-$(date +%F).tar.gz -C /data .
```

**迁移到新服务器**：复制整个 `feedback-data` 数据卷（包含数据库和自动生成的会话密钥），再启动新容器即可；如果只迁移数据库文件，用户需要重新登录。迁移后记得同步 `.env` 中的其他配置。

**开机自启**：Compose 已设置 `restart: unless-stopped`，Docker 服务启动后容器会自动恢复。Windows / macOS 需要 Docker Desktop 随系统启动。

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

公网部署前建议：

- 使用 HTTPS 反向代理或 WAF，开启 HSTS 和访问日志
- 在网关层增加登录速率限制
- 修改默认管理员密码，并妥善保管 `.env`
- 关闭不需要的游客访问或游客评论
- 定期导出数据库备份，并测试恢复流程
- 如需严格 CSP，请本地化 Tailwind 与字体资源，并移除内联 JavaScript

更完整的审计结论、修复项与残余风险见 [`AUDIT_REPORT.md`](AUDIT_REPORT.md)。

## 常见问题

### 部署相关

**提示 `docker: command not found` / `docker 不是内部或外部命令`**

Docker 未安装或未加入 PATH。安装 Docker Desktop（Windows / macOS）或 Docker Engine（Linux），安装后重新打开终端。

**提示 `Cannot connect to the Docker daemon`**

Docker 后台服务没有运行。Windows / macOS 请启动 Docker Desktop，等状态变为 Engine running；Linux 执行 `sudo systemctl start docker`。

**提示 `docker: 'compose' is not a docker command`**

Compose v2 未安装。升级 Docker Desktop，或按官方文档安装 Compose 插件。旧版 `docker-compose` 命令与本文写法不同，建议直接升级。

**Linux 提示 `permission denied while trying to connect to the Docker daemon`**

当前用户没有 Docker 权限。执行 `sudo usermod -aG docker $USER`，然后注销并重新登录；或者临时在命令前加 `sudo`。

**提示 `required variable ADMIN_PASSWORD is missing a value`**

`docker-compose.yml` 每次执行都需要读取该变量。请在项目目录创建 `.env` 并写入 `ADMIN_PASSWORD`，而不是只在某个终端里 `export`。

**日志提示 `ADMIN_PASSWORD 至少需要 12 个字符`**

初始密码太短，容器会在初始化阶段退出。修改 `.env` 后重新执行 `docker compose up -d --build`。如果之前已经生成过数据库，需要先确认管理员是否已创建；已创建后该变量不再生效。

**提示 `port is already allocated` / 端口被占用**

5000 端口被其他程序占用。可以：

- 修改 `docker-compose.yml` 中的映射为 `"8080:5000"`，执行 `docker compose up -d`，然后访问 `http://localhost:8080`
- 或找出占用进程：macOS / Linux `lsof -i :5000`，Windows `netstat -ano | findstr :5000`

macOS 的「隔空播放接收器」经常占用 5000 端口，可在「系统设置 → 通用 → 隔空投送与接力」中关闭。本地运行也可以换端口：`PORT=5001 python app.py`（Windows：`$env:PORT=5001; python app.py`）。

**容器一直 `Restarting` 或 `Exited`**

先看日志：`docker compose logs --tail=80`。常见原因包括 `ADMIN_PASSWORD` 缺失或过短、`SECRET_KEY` 显式设置但不足 32 字符、端口冲突。修复后执行 `docker compose up -d --build`。

**配置 `TRUSTED_HOSTS` 后容器显示 `unhealthy`**

容器健康检查访问的是 `http://127.0.0.1:5000/healthz`。设置 `TRUSTED_HOSTS` 时必须在列表里保留 `127.0.0.1`，否则健康检查会被拒绝。修改 `.env` 后执行 `docker compose up -d` 生效。

**拉取镜像很慢或超时**

首次构建需要从 Docker Hub 下载 Python 镜像。可在 Docker Desktop 中配置镜像加速器或网络代理，然后重新执行 `docker compose up -d --build`。

**其他设备打不开页面**

确认使用服务器 IP 而不是 `localhost`，检查云安全组、系统防火墙和 Windows 防火墙是否放行 5000；如果为了 HTTPS 把端口改成了 `127.0.0.1:5000:5000`，则只能通过反向代理访问。

**页面没有样式**

页面依赖 `cdn.tailwindcss.com` 和 `fonts.googleapis.com`。请确认网络可访问；内网或离线环境需要本地化这两个资源。

### 使用相关

**登录页看不到「游客登录」按钮**

游客访问已关闭。管理员登录后在「系统设置」中开启「允许游客访问」。

**修改了 `.env` 里的 `ADMIN_PASSWORD`，但管理员密码没变**

该变量只在数据库首次初始化时使用。已有管理员后，请登录后在「修改个人信息」中改密码。

**忘记管理员密码怎么办**

平台没有内置找回入口。若还有其他管理员账号，可由其重置；否则只能修改数据库或删除数据卷重新初始化（会丢失数据）。建议初始化后立即妥善保存密码。

**修改密码后为什么被登出了**

这是安全设计：密码修改会让旧会话和 remember token 失效，需要重新登录。

### 数据相关

**数据保存在哪里**

Docker 部署在 `feedback-data` 数据卷中（容器内 `/app/data`），本地运行在项目根目录的 `feedback.db` 和 `.secret_key`。容器删除不会丢数据，只有 `docker compose down -v` 会删除数据卷。

**如何完全重置**

Docker：`docker compose down -v`，然后重新执行 `docker compose up -d --build`。本地运行：停止程序，删除 `feedback.db`、`feedback.db-wal`、`feedback.db-shm`、`.secret_key`，再重新启动。两种方式都会丢失全部数据，操作前请先备份。

**SQLite 能支撑多大的访问量**

适合小团队、社区内部使用。项目启用了 WAL 和 30 秒锁等待，日常几十人使用没有问题；如果预期高并发或数据量很大，建议改用专业数据库或做进一步架构调整。

**如何升级到新版本**

见 [日常运维](#日常运维)。升级前先导出数据库备份，升级时不要执行 `down -v`。

## 许可证

本项目采用 GPL-3.0 许可证，详见 [`LICENSE`](LICENSE)。
