# 反馈平台

一个基于Flask和SQLite的简单反馈收集和管理平台，支持用户注册、发布反馈、评论互动等功能。

## 项目简介

该平台旨在提供一个集中收集、管理和互动反馈的系统。用户可以发布反馈意见，管理员可以对重要反馈进行置顶，所有用户可以在反馈下进行评论讨论。

### 主要特点

- 用户系统：支持注册、登录、个人信息管理
- 反馈管理：发布、查看、评论、删除反馈
- 管理功能：用户管理、内容审核、置顶重要反馈
- 权限控制：管理员、子管理员和普通用户权限分离
- 游客访问：支持游客发布反馈和评论，无需注册账户

## 安装指南

### 环境要求

- Python 3.6+
- SQLite3
- 依赖包详细列表：
  - Flask==2.3.3
  - Flask-Login==0.6.2
  - Flask-WTF==1.1.1
  - email-validator==2.0.0
  - Werkzeug==2.3.7
  - WTForms==3.0.1
  - Jinja2==3.1.2
  - MarkupSafe==2.1.3
  - itsdangerous==2.1.2
  - click==8.1.7
- Docker (如使用容器化部署)

### 本地安装步骤

1. 克隆项目到本地：
   ```
   git clone https://github.com/yourusername/feedback-platform
   cd feedback-platform
   ```

2. 创建虚拟环境（可选但推荐）：
   ```
   python -m venv venv
   # Windows激活虚拟环境
   venv\Scripts\activate
   # Linux/MacOS激活虚拟环境
   source venv/bin/activate
   ```

3. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

4. 启动应用：
   ```
   python app.py
   ```
   
   首次启动时会自动初始化数据库。

5. 访问应用：
   ```
   http://localhost:5000
   ```

### Docker部署

> **⚠️ 警告**：Docker部署方式尚未经过充分测试，可能存在未知问题。建议在测试环境中验证后再用于生产环境，请谨慎使用。

本项目支持Docker容器化部署，方便在各种环境中快速运行。

#### 使用Docker Compose (推荐)

1. 确保安装了Docker和Docker Compose
2. 克隆项目并进入项目目录：
   ```
   git clone https://github.com/yourusername/feedback-platform
   cd feedback-platform
   ```

3. 构建并启动容器：
   ```
   docker-compose up -d
   ```

4. 访问应用：
   ```
   http://localhost:5000
   ```

5. 查看日志：
   ```
   docker-compose logs -f
   ```

6. 停止应用：
   ```
   docker-compose down
   ```

#### 手动构建Docker镜像

1. 构建镜像：
   ```
   docker build -t feedback-platform .
   ```

2. 运行容器：
   ```
   docker run -d -p 5000:5000 -v feedback-data:/app/data -e SECRET_KEY=your-secure-key -e DB_DIR=/app/data --name feedback-platform feedback-platform
   ```

#### 数据持久化

Docker部署使用数据卷(volume)确保数据持久化：
- 数据库文件存储在 `/app/data` 目录
- Docker卷 `feedback-data` 被挂载到该目录
- 即使容器重新创建，数据也不会丢失

#### 环境变量配置

可在docker-compose.yml配置的环境变量：

| 变量名 | 说明 | 默认值 |
|-------|------|-------|
| SECRET_KEY | Flask密钥，用于会话安全 | your-secure-secret-key |
| FLASK_APP | Flask应用入口 | app.py |
| FLASK_ENV | 运行环境 | production |
| DB_DIR | 数据库目录 | /app/data |

## 使用指南

### 默认账户

- 管理员账户：
  - 用户名：admin
  - 密码：admin

请在首次登录后立即修改默认密码！

### 用户角色

- **普通用户**：可以发布反馈、评论，管理自己发布的内容
- **子管理员**：可以管理所有反馈和评论，可以置顶重要反馈
- **管理员**：拥有所有权限，包括用户管理、权限分配等
- **游客**：无需注册，可以直接发布反馈和评论（需管理员审核）

### 主要功能

1. **反馈管理**
   - 发布反馈：登录后可在首页点击"发布反馈"按钮
   - 置顶反馈：管理员可将重要反馈置顶显示
   - 删除反馈：用户可删除自己的反馈，管理员可删除任何反馈
   - 恢复反馈：管理员可恢复已删除的反馈
   - 审核反馈：管理员可审核游客发布的反馈

2. **用户管理**
   - 个人信息：用户可以修改个人信息和密码
   - 用户管理：管理员可以查看所有用户、编辑用户信息
   - 权限管理：管理员可提升普通用户为子管理员
   - 用户封禁：管理员可封禁违规用户并提供封禁原因

3. **评论系统**
   - 发表评论：用户可在反馈下发表评论
   - 回复评论：支持对特定评论进行回复
   - 删除评论：用户可删除自己的评论，管理员可删除任何评论
   - 恢复评论：管理员可恢复已删除的评论
   - 审核评论：管理员可审核游客发表的评论

4. **游客功能**
   - 游客反馈：无需注册即可发布反馈（需管理员审核）
   - 游客评论：无需注册即可发表评论（可能需要管理员审核，取决于系统设置）
   - 游客登录：可使用游客账户直接登录体验系统

5. **系统设置**
   - 平台名称：管理员可自定义平台显示名称
   - 游客权限：管理员可控制是否允许游客发布内容及是否需要审核

## 技术架构

- **后端**：Flask框架
- **数据库**：SQLite
- **前端**：HTML, CSS (Tailwind CSS), JavaScript
- **认证**：Flask-Login
- **容器化**：Docker, Docker Compose

## 项目结构

```
feedback-platform/
├── app.py                # 主应用入口
├── config.py             # 配置文件
├── models.py             # 数据库模型（含初始化）
├── forms.py              # 表单定义
├── feedback.db           # SQLite数据库文件
├── requirements.txt      # 依赖列表
├── Dockerfile            # Docker构建文件
├── docker-compose.yml    # Docker Compose配置
├── .dockerignore         # Docker构建忽略文件
├── static/               # 静态资源
│   ├── css/              # 样式文件
│   ├── js/               # JavaScript文件
│   └── images/           # 图片资源
└── templates/            # HTML模板
```

## 本地开发指南

1. **数据库操作**
   - 数据库文件位于项目根目录：`feedback.db`
   - 可使用 SQLite Browser 等工具查看和编辑数据库
   - 数据库结构在 `models.py` 中定义

2. **新功能开发**
   - 前端模板在 `templates/` 目录
   - 静态资源在 `static/` 目录
   - 应用逻辑在 `app.py` 中
   - 表单定义在 `forms.py` 中

3. **调试技巧**
   - 开发模式下启动：`FLASK_ENV=development python app.py`
   - 设置环境变量可以开启详细日志：`FLASK_DEBUG=1`

## 生产环境注意事项

1. **安全设置**：
   - 修改docker-compose.yml中的SECRET_KEY为强密码
   - 使用HTTPS反向代理保护应用（可配置Nginx）
   - 确保重要路径如`/admin`受到适当保护

2. **性能优化**：
   - 对于大型部署，建议使用更强大的数据库（如PostgreSQL）
   - 考虑使用Redis缓存频繁访问的内容
   - 可集成CDN加速静态资源

3. **备份策略**：
   - 定期备份Docker卷中的数据库文件
   - 可配置自动备份脚本：
     ```
     docker run --rm -v feedback-data:/data -v /backup:/backup alpine sh -c "tar -czf /backup/feedback-db-$(date +%Y%m%d).tar.gz /data"
     ```
   - 建议至少保留近7天的备份

## 常见问题解答

1. **Q: 如何重置管理员密码？**
   A: 直接编辑数据库中的user表，或者通过Python shell访问User模型设置新密码。

2. **Q: 游客发布的内容在哪里审核？**
   A: 管理员可以在首页通过"查看待审核内容"选项来审核游客发布的反馈。

3. **Q: 如何调整每页显示的反馈数量？**
   A: 在config.py文件中修改POSTS_PER_PAGE参数。

## 开发者信息

该平台为学习/演示项目，欢迎提出改进建议和贡献代码。如需贡献，请fork本项目并提交Pull Request。

## 更新日志

- **v1.0.0** (2023-04-01): 初始版本发布
  - 基本用户系统
  - 反馈发布和管理
  - 评论系统
  
- **v1.1.0** (2023-04-03): 功能增强
  - 添加游客访问模式
  - 增加内容审核功能
  - Docker部署支持

---

# Feedback Platform

A simple feedback collection and management platform based on Flask and SQLite, supporting user registration, feedback submission, and interactive commenting.

## Project Overview

This platform aims to provide a centralized system for collecting, managing, and interacting with feedback. Users can submit feedback, admins can pin important posts, and all users can engage in discussions through comments.

### Key Features

- User system: Registration, login, and profile management
- Feedback management: Submission, viewing, commenting, and deletion
- Administration: User management, content moderation, and pinning important feedbacks
- Permission control: Separate permissions for admins, sub-admins, and regular users
- Guest access: Option to post feedback and comments without registration

## Installation Guide

### Requirements

- Python 3.6+
- SQLite3
- Required packages:
  - Flask==2.3.3
  - Flask-Login==0.6.2
  - Flask-WTF==1.1.1
  - email-validator==2.0.0
  - Werkzeug==2.3.7
  - WTForms==3.0.1
  - Jinja2==3.1.2
  - MarkupSafe==2.1.3
  - itsdangerous==2.1.2
  - click==8.1.7
- Docker (for containerized deployment)

### Local Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/feedback-platform
   cd feedback-platform
   ```

2. Create virtual environment (optional but recommended):
   ```
   python -m venv venv
   # Activate on Windows
   venv\Scripts\activate
   # Activate on Linux/MacOS
   source venv/bin/activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Launch application:
   ```
   python app.py
   ```
   The database will auto-initialize on first launch.

5. Access at:
   ```
   http://localhost:5000
   ```

### Docker Deployment

> **⚠️ Warning**: Docker deployment hasn't been thoroughly tested. Please validate in test environments before production use.

#### Using Docker Compose (Recommended)

1. Ensure Docker and Docker Compose are installed
2. Clone repository:
   ```
   git clone https://github.com/yourusername/feedback-platform
   cd feedback-platform
   ```

3. Build and start containers:
   ```
   docker-compose up -d
   ```

4. Access application:
   ```
   http://localhost:5000
   ```

5. View logs:
   ```
   docker-compose logs -f
   ```

6. Stop application:
   ```
   docker-compose down
   ```

#### Manual Docker Build

1. Build image:
   ```
   docker build -t feedback-platform .
   ```

2. Run container:
   ```
   docker run -d -p 5000:5000 -v feedback-data:/app/data -e SECRET_KEY=your-secure-key -e DB_DIR=/app/data --name feedback-platform feedback-platform
   ```

#### Data Persistence

Docker deployment uses volumes for persistence:
- Database stored in `/app/data`
- Mounted via `feedback-data` volume
- Data survives container recreation

#### Environment Variables

Configurable in docker-compose.yml:

| Variable | Description | Default |
|---------|------------|---------|
| SECRET_KEY | Flask secret key | your-secure-secret-key |
| FLASK_APP | Entry point | app.py |
| FLASK_ENV | Environment | production |
| DB_DIR | Database directory | /app/data |

## User Guide

### Default Accounts

- Admin account:
  - Username: admin
  - Password: admin

Change default password immediately after first login!

### User Roles

- **Regular Users**: Can post feedback, comment, and manage own content
- **Sub-Admins**: Can manage all feedback and comments, pin important posts
- **Admins**: Full permissions including user management
- **Guests**: Can post without registration (subject to admin approval)

### Core Features

1. **Feedback Management**
   - Submit feedback via "Post Feedback" button
   - Pin important posts (admin)
   - Delete feedback (owners or admins)
   - Restore deleted feedback (admins)
   - Moderate guest submissions (admins)

2. **User Management**
   - Profile editing
   - User administration (admins)
   - Permission management (admins)
   - User banning with reasons (admins)

3. **Comment System**
   - Post comments
   - Reply to specific comments
   - Delete comments (owners or admins)
   - Restore comments (admins)
   - Moderate guest comments (admins)

4. **Guest Features**
   - Post feedback without registration
   - Comment without registration
   - Guest login option

5. **System Settings**
   - Platform name customization
   - Guest permissions configuration

## Technical Architecture

- **Backend**: Flask framework
- **Database**: SQLite
- **Frontend**: HTML, CSS (Tailwind CSS), JavaScript
- **Authentication**: Flask-Login
- **Containerization**: Docker, Docker Compose

## Project Structure

```
feedback-platform/
├── app.py                # Main application
├── config.py             # Configuration
├── models.py             # DB models
├── forms.py              # Forms
├── feedback.db           # SQLite DB
├── requirements.txt      # Dependencies
├── Dockerfile            # Docker build
├── docker-compose.yml    # Docker Compose
├── .dockerignore         # Docker exclusions
├── static/               # Static assets
│   ├── css/              # Styles
│   ├── js/               # JavaScript
│   └── images/           # Images
└── templates/            # HTML templates
```

## Development Guide

1. **Database Operations**
   - Database file: `feedback.db`
   - Use SQLite Browser for inspection
   - Schema defined in `models.py`

2. **Feature Development**
   - Templates in `templates/`
   - Static assets in `static/`
   - Application logic in `app.py`
   - Forms in `forms.py`

3. **Debugging**
   - Development mode: `FLASK_ENV=development python app.py`
   - Verbose logging: `FLASK_DEBUG=1`

## Production Considerations

1. **Security**
   - Set strong SECRET_KEY in docker-compose.yml
   - Use HTTPS via reverse proxy (e.g., Nginx)
   - Protect sensitive routes like `/admin`

2. **Performance**
   - Consider PostgreSQL for large deployments
   - Implement Redis for caching
   - Use CDN for static assets

3. **Backups**
   - Regularly back up Docker volumes
   - Sample backup script:
     ```
     docker run --rm -v feedback-data:/data -v /backup:/backup alpine sh -c "tar -czf /backup/feedback-db-$(date +%Y%m%d).tar.gz /data"
     ```
   - Maintain at least 7 days of backups

## FAQ

1. **Q: How to reset admin password?**
   A: Edit user table directly or reset via Python shell.

2. **Q: Where to moderate guest submissions?**
   A: Via "Pending Content" section on admin dashboard.

3. **Q: How to adjust posts per page?**
   A: Modify POSTS_PER_PAGE in config.py.

## Developer Information

This is a learning/demonstration project. Contributions via Pull Requests are welcome.

## Changelog

- **v1.0.0** (2023-04-01): Initial release
  - Basic user system
  - Feedback management
  - Comment system

- **v1.1.0** (2023-04-03): Enhancements
  - Guest access mode
  - Content moderation
  - Docker support