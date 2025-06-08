# 反馈平台

一个基于Flask和SQLite的简单反馈收集和管理平台，支持用户注册、发布反馈、评论互动等功能。

## 项目简介

该平台旨在提供一个集中收集、管理和互动反馈的系统。用户可以发布反馈意见，管理员可以对重要反馈进行置顶，所有用户可以在反馈下进行评论讨论。

### 主要功能

- 🔐 **用户系统**：支持注册、登录、个人信息管理
- 📝 **反馈管理**：发布、查看、评论、删除反馈
- 👨‍💼 **管理功能**：用户管理、内容审核、置顶重要反馈
- 🔑 **权限控制**：管理员、子管理员和普通用户权限分离
- 👤 **游客访问**：支持游客发布反馈和评论，无需注册账户

### 技术栈

- **后端**：Flask + SQLite
- **前端**：HTML + CSS (Tailwind CSS) + JavaScript
- **认证**：Flask-Login
- **容器化**：Docker + Docker Compose

## Docker Compose 部署（推荐）

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+

### 部署步骤

1. **安装Docker环境**
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   
   # 重新登录或执行
   newgrp docker
   ```

2. **克隆项目**
   ```bash
   git clone https://github.com/Qianxia666/feedback-platform.git
   cd feedback-platform
   ```

3. **启动服务**
   ```bash
   # 后台启动
   docker-compose up -d
   
   # 查看启动状态
   docker-compose ps
   ```

4. **访问应用**
   - 地址：http://localhost:5000
   - 默认管理员账户：`admin` / `admin`
   - ⚠️ **请立即修改默认密码！**


## 本地开发

### 环境要求

- Python 3.8+
- pip

### 开发步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/Qianxia666/feedback-platform.git
   cd feedback-platform
   ```

4. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

5. **启动开发服务器**
   ```bash
   python app.py
   ```

6. **访问应用**
   - 地址：http://localhost:5000
   - 开发模式支持热重载
   - 默认管理员账户：`admin` / `admin`

## 项目结构

```
feedback-platform/
├── app.py                # 主应用入口
├── config.py             # 配置文件
├── models.py             # 数据库模型
├── forms.py              # 表单定义
├── requirements.txt      # 依赖列表
├── Dockerfile            # Docker构建文件
├── docker-compose.yml    # Docker Compose配置
├── static/               # 静态资源
│   ├── css/              # 样式文件
│   └── js/               # JavaScript文件
└── templates/            # HTML模板
```

## 默认账户

- **管理员账户**：
  - 用户名：`admin`
  - 密码：`admin`
  - ⚠️ **请在首次登录后立即修改默认密码！**

## 用户角色

| 角色 | 权限说明 |
|------|----------|
| 👤 **普通用户** | 发布反馈、评论，管理自己的内容 |
| 👨‍💼 **子管理员** | 管理所有反馈和评论，置顶重要反馈 |
| 👑 **管理员** | 拥有所有权限，包括用户管理、权限分配 |
| 🚶 **游客** | 无需注册，可发布反馈和评论（需审核） |
