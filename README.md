# 反馈平台

一个基于Flask和SQLite的简单反馈收集和管理平台，支持用户注册、发布反馈、评论互动等功能。

## 项目简介

该平台旨在提供一个集中收集、管理和互动反馈的系统。用户可以发布反馈意见，管理员可以对重要反馈进行置顶，所有用户可以在反馈下进行评论讨论。

### 主要特点

- 用户系统：支持注册、登录、个人信息管理
- 反馈管理：发布、查看、评论、删除反馈
- 管理功能：用户管理、内容审核、置顶重要反馈
- 权限控制：管理员、子管理员和普通用户权限分离

## 安装指南

### 环境要求

- Python 3.6+
- Flask 2.3.3+
- SQLite3
- Docker (如使用容器化部署)

### 本地安装步骤

1. 克隆项目到本地：
   ```
   git clone https://github.com/Qianxia666/feedback-platform
   cd feedback-platform
   ```

2. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

3. 启动应用：
   ```
   python app.py
   ```
   
   首次启动时会自动初始化数据库。

4. 访问应用：
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
   git clone https://github.com/Qianxia666/feedback-platform
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

### 默认管理员账户

- 用户名：admin
- 密码：admin123

请在首次登录后立即修改默认密码！

### 用户角色

- **普通用户**：可以发布反馈、评论，管理自己发布的内容
- **子管理员**：可以管理所有反馈和评论，可以置顶重要反馈
- **管理员**：拥有所有权限，包括用户管理、权限分配等

### 主要功能

1. **反馈管理**
   - 发布反馈：登录后可在首页点击"发布反馈"按钮
   - 置顶反馈：管理员可将重要反馈置顶显示
   - 删除反馈：用户可删除自己的反馈，管理员可删除任何反馈
   - 恢复反馈：管理员可恢复已删除的反馈

2. **用户管理**
   - 个人信息：用户可以修改个人信息和密码
   - 用户管理：管理员可以查看所有用户、编辑用户信息
   - 权限管理：管理员可提升普通用户为子管理员
   - 用户封禁：管理员可封禁违规用户并提供封禁原因

3. **评论系统**
   - 发表评论：用户可在反馈下发表评论
   - 删除评论：用户可删除自己的评论，管理员可删除任何评论
   - 恢复评论：管理员可恢复已删除的评论

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
├── requirements.txt      # 依赖列表
├── Dockerfile            # Docker构建文件
├── docker-compose.yml    # Docker Compose配置
├── .dockerignore         # Docker构建忽略文件
├── static/               # 静态资源
└── templates/            # HTML模板
```

## 生产环境注意事项

1. **安全设置**：
   - 修改docker-compose.yml中的SECRET_KEY为强密码
   - 使用HTTPS反向代理保护应用（可配置Nginx）

2. **性能优化**：
   - 对于大型部署，建议使用更强大的数据库（如PostgreSQL）
   - 考虑使用Redis缓存频繁访问的内容

3. **备份策略**：
   - 定期备份Docker卷中的数据库文件
   - 可配置自动备份脚本：
     ```
     docker run --rm -v feedback-data:/data -v /backup:/backup alpine sh -c "tar -czf /backup/feedback-db-$(date +%Y%m%d).tar.gz /data"
     ```

## 开发者信息

该平台为学习/演示项目，欢迎提出改进建议和贡献代码。如需贡献，请fork本项目并提交Pull Request。

---

# Feedback Platform

A simple feedback collection and management platform based on Flask and SQLite, supporting user registration, feedback posting, comment interaction, and more.

## Project Introduction

This platform aims to provide a centralized system for collecting, managing, and interacting with feedback. Users can publish feedback, administrators can pin important feedback, and all users can engage in discussions through comments.

### Key Features

- User System: Supports registration, login, and personal information management
- Feedback Management: Publish, view, comment on, and delete feedback
- Administration: User management, content moderation, pinning important feedback
- Permission Control: Separation of admin, sub-admin, and regular user permissions

## Installation Guide

### Requirements

- Python 3.6+
- Flask 2.3.3+
- SQLite3
- Docker (for containerized deployment)

### Local Installation

1. Clone the repository:
   ```
   git clone https://github.com/Qianxia666/feedback-platform
   cd feedback-platform
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Launch the application:
   ```
   python app.py
   ```
   
   The database will be automatically initialized on first launch.

4. Access the application:
   ```
   http://localhost:5000
   ```

### Docker Deployment

> **⚠️ Warning**: Docker deployment has not been thoroughly tested and may contain unknown issues. It's recommended to validate in a testing environment before using in production. Please use with caution.

This project supports Docker containerization for easy deployment in various environments.

#### Using Docker Compose (Recommended)

1. Ensure Docker and Docker Compose are installed
2. Clone the repository and navigate to the project directory:
   ```
   git clone https://github.com/Qianxia666/feedback-platform
   cd feedback-platform
   ```

3. Build and start the container:
   ```
   docker-compose up -d
   ```

4. Access the application:
   ```
   http://localhost:5000
   ```

5. View logs:
   ```
   docker-compose logs -f
   ```

6. Stop the application:
   ```
   docker-compose down
   ```

#### Manual Docker Image Building

1. Build the image:
   ```
   docker build -t feedback-platform .
   ```

2. Run the container:
   ```
   docker run -d -p 5000:5000 -v feedback-data:/app/data -e SECRET_KEY=your-secure-key -e DB_DIR=/app/data --name feedback-platform feedback-platform
   ```

#### Data Persistence

Docker deployment uses volumes to ensure data persistence:
- Database files are stored in the `/app/data` directory
- The Docker volume `feedback-data` is mounted to this directory
- Data will not be lost even if the container is recreated

#### Environment Variables

Environment variables that can be configured in docker-compose.yml:

| Variable | Description | Default Value |
|----------|-------------|---------------|
| SECRET_KEY | Flask key for session security | your-secure-secret-key |
| FLASK_APP | Flask application entry point | app.py |
| FLASK_ENV | Running environment | production |
| DB_DIR | Database directory | /app/data |

## User Guide

### Default Admin Account

- Username: admin
- Password: admin123

Please change the default password immediately after first login!

### User Roles

- **Regular Users**: Can post feedback, comment, and manage their own content
- **Sub-Administrators**: Can manage all feedback and comments, can pin important feedback
- **Administrators**: Have full permissions, including user management and permission assignment

### Main Features

1. **Feedback Management**
   - Post Feedback: After logging in, click the "Post Feedback" button on the homepage
   - Pin Feedback: Administrators can pin important feedback to the top
   - Delete Feedback: Users can delete their own feedback, administrators can delete any feedback
   - Restore Feedback: Administrators can restore deleted feedback

2. **User Management**
   - Personal Information: Users can modify their personal information and password
   - User Management: Administrators can view all users and edit user information
   - Permission Management: Administrators can promote regular users to sub-administrators
   - User Banning: Administrators can ban users who violate rules and provide a reason

3. **Comment System**
   - Post Comments: Users can comment on feedback
   - Delete Comments: Users can delete their own comments, administrators can delete any comment
   - Restore Comments: Administrators can restore deleted comments

## Technical Architecture

- **Backend**: Flask framework
- **Database**: SQLite
- **Frontend**: HTML, CSS (Tailwind CSS), JavaScript
- **Authentication**: Flask-Login
- **Containerization**: Docker, Docker Compose

## Project Structure

```
feedback-platform/
├── app.py                # Main application entry
├── config.py             # Configuration file
├── models.py             # Database models (with initialization)
├── forms.py              # Form definitions
├── requirements.txt      # Dependencies list
├── Dockerfile            # Docker build file
├── docker-compose.yml    # Docker Compose configuration
├── .dockerignore         # Docker build ignore file
├── static/               # Static resources
└── templates/            # HTML templates
```

## Production Environment Considerations

1. **Security Settings**:
   - Change the SECRET_KEY in docker-compose.yml to a strong password
   - Use HTTPS reverse proxy to protect the application (Nginx can be configured)

2. **Performance Optimization**:
   - For large-scale deployments, consider using a more powerful database (like PostgreSQL)
   - Consider using Redis to cache frequently accessed content

3. **Backup Strategy**:
   - Regularly backup the database files in the Docker volume
   - Configure an automatic backup script:
     ```
     docker run --rm -v feedback-data:/data -v /backup:/backup alpine sh -c "tar -czf /backup/feedback-db-$(date +%Y%m%d).tar.gz /data"
     ```

## Developer Information

This platform is a learning/demonstration project. Suggestions for improvement and code contributions are welcome. To contribute, please fork this project and submit a Pull Request. 