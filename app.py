from flask import (Flask, render_template, flash, redirect, url_for, request,
                   abort, session, g, has_request_context, send_file)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from markupsafe import Markup, escape
from urllib.parse import urlsplit
from config import Config
from models import (User, Post, Comment, Pagination, init_db, get_db_connection,
                    ActivityLog, Settings)
from forms import LoginForm, RegisterForm, PostForm, CommentForm, EditProfileForm, AdminEditProfileForm, BanUserForm
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
import pytz

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    CSRFProtect(app)

    def clamp_page(requested_page, total, per_page):
        pages = max(1, (total + per_page - 1) // per_page)
        return min(max(1, requested_page), pages)

    def nullable_bool(value):
        return None if value is None else bool(value)
    
    # 添加nl2br过滤器
    @app.template_filter('nl2br')
    def nl2br_filter(s):
        if not s:
            return ''
        return Markup('<br>\n').join(escape(s).splitlines())
    
    # 添加日期格式化过滤器
    @app.template_filter('format_datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        if value is None:
            return ''

        try:
            settings = getattr(g, 'settings', {}) if has_request_context() else {}
            timezone_setting = settings.get('timezone', 'Asia/Shanghai')
            try:
                target_tz = pytz.timezone(timezone_setting)
            except pytz.UnknownTimeZoneError:
                target_tz = pytz.timezone('Asia/Shanghai')

            # 处理字符串时间
            if isinstance(value, str):
                try:
                    # 尝试解析ISO格式时间
                    if 'T' in value:
                        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                    else:
                        # 尝试解析数据库格式时间
                        value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                        # 假设数据库时间是UTC
                        value = value.replace(tzinfo=dt_timezone.utc)
                except (ValueError, AttributeError):
                    return value

            # 如果没有时区信息，假设是UTC
            if hasattr(value, 'tzinfo') and value.tzinfo is None:
                value = value.replace(tzinfo=dt_timezone.utc)

            # 转换到目标时区
            if hasattr(value, 'astimezone'):
                value = value.astimezone(target_tz)

            return value.strftime(format)

        except (AttributeError, ValueError, TypeError, ImportError, OverflowError):
            # 如果转换失败，使用原始格式
            try:
                if hasattr(value, 'strftime'):
                    return value.strftime(format)
                else:
                    return str(value)
            except (AttributeError, ValueError):
                return str(value)
    
    # 初始化数据库
    init_db()
    
    # 初始化登录管理器
    login_manager = LoginManager(app)
    login_manager.login_view = 'login'
    login_manager.login_message = '请先登录以访问此页面'
    
    @login_manager.user_loader
    def load_user(id):
        try:
            return User.get_by_id(int(id))
        except (TypeError, ValueError):
            return None
    
    # 每次请求前更新用户最后活跃时间并加载设置
    @app.before_request
    def before_request():
        if request.endpoint == 'static':
            return None
        g.settings = Settings.get_dict()
        if current_user.is_authenticated:
            # 如果用户被封禁，强制登出
            if current_user.is_banned and request.endpoint not in ['logout', 'static']:
                flash('您的账号已被封禁，无法继续使用。如有疑问，请联系管理员。')
                logout_user()
                return redirect(url_for('login'))
            if (current_user.username == 'tourist'
                    and g.settings.get('allow_tourist', 'true') != 'true'
                    and request.endpoint != 'logout'):
                logout_user()
                flash('管理员已关闭游客访问，请使用注册账号')
                return redirect(url_for('login'))
            current_user.update_last_seen()
        # 检查用户登录状态
        if not current_user.is_authenticated and request.endpoint not in ['login', 'register', 'static', 'logout', 'tourist_login'] and not request.path.startswith('/static/'):
            flash('请先登录再访问此页面')
            return redirect(url_for('login', next=request.full_path))
    
    # 添加全局模板变量
    @app.context_processor
    def inject_settings():
        settings = getattr(g, 'settings', None)
        if settings is None:
            settings = Settings.get_dict()
        return {
            'platform_name': settings.get('platform_name', '反馈平台'),
            'allow_tourist': settings.get('allow_tourist', 'true'),
            'allow_tourist_comment': settings.get('allow_tourist_comment', 'true'),
            'max_comment_depth': app.config['MAX_COMMENT_DEPTH'],
        }
    
    # 首页 - 显示所有反馈
    @app.route('/')
    @app.route('/index')
    def index():
        page = max(1, request.args.get('page', 1, type=int))
        include_deleted = False
        include_pending = False
        pending_count = 0
        
        if current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin):
            include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
            include_pending = request.args.get('include_pending', 'false').lower() == 'true'
            if include_pending:
                include_deleted = False
            
            # 获取待审核帖子数量
            conn = get_db_connection()
            pending_count = conn.execute('SELECT COUNT(*) FROM post WHERE is_tourist_post = 1 AND is_approved IS NULL AND is_deleted = 0').fetchone()[0]
            conn.close()
            
        # 如果是管理员并且要查看待审核帖子
        if include_pending and current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin):
            conn = get_db_connection()
            
            total_query = 'SELECT COUNT(*) FROM post WHERE is_tourist_post = 1 AND is_approved IS NULL AND is_deleted = 0'
            total = conn.execute(total_query).fetchone()[0]
            page = clamp_page(page, total, app.config['POSTS_PER_PAGE'])
            offset = (page - 1) * app.config['POSTS_PER_PAGE']
            posts_query = 'SELECT * FROM post WHERE is_tourist_post = 1 AND is_approved IS NULL AND is_deleted = 0 ORDER BY created_at DESC LIMIT ? OFFSET ?'
            
            posts_data = conn.execute(posts_query, (app.config['POSTS_PER_PAGE'], offset)).fetchall()
            
            posts = []
            for post_data in posts_data:
                posts.append(Post(
                    id=post_data['id'],
                    title=post_data['title'],
                    content=post_data['content'],
                    created_at=post_data['created_at'],
                    user_id=post_data['user_id'],
                    is_deleted=bool(post_data['is_deleted']) if 'is_deleted' in post_data.keys() else False,
                    deleted_at=post_data['deleted_at'] if 'deleted_at' in post_data.keys() else None,
                    deleted_by=post_data['deleted_by'] if 'deleted_by' in post_data.keys() else None,
                    is_pinned=bool(post_data['is_pinned']) if 'is_pinned' in post_data.keys() else False,
                    is_tourist_post=bool(post_data['is_tourist_post']) if 'is_tourist_post' in post_data.keys() else False,
                    is_approved=nullable_bool(post_data['is_approved']) if 'is_approved' in post_data.keys() else None
                ))
            
            # 创建分页对象
            Post.preload(posts)
            posts = Pagination(page, app.config['POSTS_PER_PAGE'], total, posts)
            conn.close()
            
            return render_template('index.html', title='待审核反馈', posts=posts, include_deleted=include_deleted, include_pending=include_pending, pending_count=pending_count)
        else:
            if include_deleted and current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin):
                # 显示所有已删除的帖子
                conn = get_db_connection()
                total = conn.execute('SELECT COUNT(*) FROM post WHERE is_deleted = 1').fetchone()[0]
                page = clamp_page(page, total, app.config['POSTS_PER_PAGE'])
                offset = (page - 1) * app.config['POSTS_PER_PAGE']
                posts_data = conn.execute(
                    'SELECT * FROM post WHERE is_deleted = 1 ORDER BY created_at DESC LIMIT ? OFFSET ?',
                    (app.config['POSTS_PER_PAGE'], offset)
                ).fetchall()
                
                posts = []
                for post_data in posts_data:
                    posts.append(Post(
                        id=post_data['id'],
                        title=post_data['title'],
                        content=post_data['content'],
                        created_at=post_data['created_at'],
                        user_id=post_data['user_id'],
                        is_deleted=bool(post_data['is_deleted']) if 'is_deleted' in post_data.keys() else False,
                        deleted_at=post_data['deleted_at'] if 'deleted_at' in post_data.keys() else None,
                        deleted_by=post_data['deleted_by'] if 'deleted_by' in post_data.keys() else None,
                        is_pinned=bool(post_data['is_pinned']) if 'is_pinned' in post_data.keys() else False,
                        is_tourist_post=bool(post_data['is_tourist_post']) if 'is_tourist_post' in post_data.keys() else False,
                        is_approved=nullable_bool(post_data['is_approved']) if 'is_approved' in post_data.keys() else None
                    ))
                
                Post.preload(posts)
                posts = Pagination(page, app.config['POSTS_PER_PAGE'], total, posts)
                conn.close()
                
                return render_template('index.html', title='已删除反馈', posts=posts, include_deleted=include_deleted, include_pending=include_pending, pending_count=pending_count)
            else:
                posts = Post.get_all(page=page, per_page=app.config['POSTS_PER_PAGE'], include_deleted=include_deleted)
                return render_template('index.html', title='反馈广场', posts=posts, include_deleted=include_deleted, include_pending=include_pending, pending_count=pending_count)
    


    # 登录
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))

        # 清除重复的登录提示消息
        messages = session.get('_flashes', [])
        unique_messages = []
        seen_messages = set()
        for category, message in messages:
            if message not in seen_messages:
                unique_messages.append((category, message))
                seen_messages.add(message)
        session['_flashes'] = unique_messages

        form = LoginForm()
        if form.validate_on_submit():
            user = User.get_by_username(form.username.data)
            if user is None or not user.check_password(form.password.data):
                flash('用户名或密码错误')
                return redirect(url_for('login'))
            if user.is_banned:
                flash('您的账号已被封禁，无法登录。如有疑问，请联系管理员。')
                return redirect(url_for('login'))
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            parsed_next = urlsplit(next_page or '')
            if (not next_page or parsed_next.scheme or parsed_next.netloc
                    or not parsed_next.path.startswith('/')
                    or next_page.startswith('//') or '\\' in next_page):
                next_page = url_for('index')
            flash(f'欢迎, {user.username}!')
            return redirect(next_page)
        return render_template('login.html', title='登录', form=form)

    # 游客登录
    @app.route('/tourist-login', methods=['POST'])
    def tourist_login():
        # 检查是否允许游客登录
        allow_tourist = g.settings.get('allow_tourist', 'true')
        if allow_tourist != 'true':
            flash('管理员已禁止游客登录，请使用注册账号')
            return redirect(url_for('login'))
            
        if current_user.is_authenticated:
            logout_user()  # 先注销当前用户
        
        # 获取游客账户
        tourist = User.get_by_username('tourist')
        if not tourist:
            # 如果游客账户不存在，创建游客账户
            tourist = User(username='tourist', email='tourist@example.com')
            tourist.set_password(os.urandom(32).hex())
            try:
                tourist.save()
            except sqlite3.IntegrityError:
                tourist = User.get_by_username('tourist')
        if tourist.is_banned:
            flash('游客账户当前不可用，请注册账号')
            return redirect(url_for('login'))

        login_user(tourist, remember=False)
        flash('您已以游客身份登录')
        return redirect(url_for('index'))
    
    # 注册
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        form = RegisterForm()
        if form.validate_on_submit():
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            try:
                user.save()
            except sqlite3.IntegrityError:
                flash('用户名或邮箱已被使用')
                return redirect(url_for('register'))
            flash('注册成功，现在可以登录了!')
            return redirect(url_for('login'))
        return render_template('register.html', title='注册', form=form)
    
    # 注销
    @app.route('/logout', methods=['POST'])
    @login_required
    def logout():
        logout_user()
        flash('已成功注销')
        return redirect(url_for('login'))
    
    # 用户个人主页
    @app.route('/user/<username>')
    def user_profile(username):
        user = User.get_by_username(username)
        if not user:
            abort(404)
        
        # 获取用户所有帖子，管理员可以看到已删除的帖子
        conn = get_db_connection()
        if current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin):
            user_posts = conn.execute(
                'SELECT * FROM post WHERE user_id = ? ORDER BY is_pinned DESC, created_at DESC',
                (user.id,)
            ).fetchall()
        else:
            user_posts = conn.execute(
                '''SELECT * FROM post
                   WHERE user_id = ? AND is_deleted = 0
                     AND (is_tourist_post = 0 OR is_approved = 1)
                   ORDER BY is_pinned DESC, created_at DESC''',
                (user.id,)
            ).fetchall()
        
        result_posts = []
        for post in user_posts:
            result_posts.append(Post(
                id=post['id'],
                title=post['title'],
                content=post['content'],
                created_at=post['created_at'],
                user_id=post['user_id'],
                is_deleted=bool(post['is_deleted']) if 'is_deleted' in post.keys() else False,
                deleted_at=post['deleted_at'] if 'deleted_at' in post.keys() else None,
                deleted_by=post['deleted_by'] if 'deleted_by' in post.keys() else None,
                is_pinned=bool(post['is_pinned']) if 'is_pinned' in post.keys() else False
            ))
        # 获取用户所有评论，管理员可以看到已删除的评论
        if current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin):
            user_comments = conn.execute(
                'SELECT c.*, p.title as post_title FROM comment c JOIN post p ON c.post_id = p.id WHERE c.user_id = ? ORDER BY c.created_at DESC',
                (user.id,)
            ).fetchall()
        else:
            user_comments = conn.execute(
                '''SELECT c.*, p.title as post_title FROM comment c
                   JOIN post p ON c.post_id = p.id
                   WHERE c.user_id = ? AND c.is_deleted = 0 AND p.is_deleted = 0
                     AND (p.is_tourist_post = 0 OR p.is_approved = 1)
                   ORDER BY c.created_at DESC''',
                (user.id,)
            ).fetchall()
        
        result_comments = []
        for comment in user_comments:
            comment_object = Comment(
                id=comment['id'],
                content=comment['content'],
                created_at=comment['created_at'],
                user_id=comment['user_id'],
                post_id=comment['post_id'],
                is_deleted=bool(comment['is_deleted']) if 'is_deleted' in comment.keys() else False,
                deleted_at=comment['deleted_at'] if 'deleted_at' in comment.keys() else None,
                deleted_by=comment['deleted_by'] if 'deleted_by' in comment.keys() else None
            )
            comment_object._post = Post(
                id=comment['post_id'], title=comment['post_title']
            )
            result_comments.append(comment_object)
        
        conn.close()
        
        return render_template('user_profile.html', user=user, user_posts=result_posts, user_comments=result_comments)
    
    # 编辑个人信息
    @app.route('/edit-profile', methods=['GET', 'POST'])
    @login_required
    def edit_profile():
        # 禁止游客修改个人信息
        if current_user.username == 'tourist':
            flash('游客账户不能修改个人信息')
            return redirect(url_for('user_profile', username=current_user.username))
            
        form = EditProfileForm(current_user.username, current_user.email)
        if form.validate_on_submit():
            if (current_user.username == 'admin'
                    and form.username.data != current_user.username):
                flash('系统管理员账号不能更改用户名')
                return redirect(url_for('edit_profile'))
            # 验证当前密码
            if form.password.data and not form.current_password.data:
                flash('修改密码前请输入当前密码')
                return redirect(url_for('edit_profile'))
            if form.current_password.data and not current_user.check_password(form.current_password.data):
                flash('当前密码不正确')
                return redirect(url_for('edit_profile'))
            
            # 记录修改内容
            changed_fields = []
            if current_user.username != form.username.data:
                changed_fields.append(f"用户名从 {current_user.username} 修改为 {form.username.data}")
            
            if current_user.email != form.email.data:
                changed_fields.append(f"邮箱从 {current_user.email} 修改为 {form.email.data}")
            
            if form.password.data:
                changed_fields.append("修改了密码")
            
            # 保存修改
            current_user.username = form.username.data
            current_user.email = form.email.data
            
            # 更新密码
            if form.password.data:
                current_user.set_password(form.password.data)
            
            try:
                current_user.save()
            except sqlite3.IntegrityError:
                flash('用户名或邮箱已被使用')
                return redirect(url_for('edit_profile'))
            
            # 记录操作日志
            if changed_fields:
                description = "修改了个人信息: " + ", ".join(changed_fields)
                ActivityLog.create_log(
                    user_id=current_user.id,
                    action='user_edit_profile',
                    target_type='user',
                    target_id=current_user.id,
                    description=description
                )
            
            flash('个人信息已更新')
            return redirect(url_for('user_profile', username=current_user.username))
        elif request.method == 'GET':
            form.username.data = current_user.username
            form.email.data = current_user.email
        
        return render_template('edit_profile.html', title='编辑个人信息', form=form)
    
    # 管理员用户管理列表
    @app.route('/admin/users')
    @login_required
    def admin_users():
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限访问此页面')
            return redirect(url_for('index'))
        
        page = max(1, request.args.get('page', 1, type=int))
        users = User.get_all(page=page, per_page=app.config.get('USERS_PER_PAGE', 10))
        
        return render_template('admin/users.html', title='用户管理', users=users)
    
    # 管理员编辑用户
    @app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_user(user_id):
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限访问此页面')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        
        # 子管理员不能编辑管理员
        if current_user.is_sub_admin and user.is_admin:
            flash('您没有权限编辑管理员账户')
            return redirect(url_for('admin_users'))
        
        form = AdminEditProfileForm(user.username, user.email)
        if form.validate_on_submit():
            if (user.username in {'admin', 'tourist'}
                    and form.username.data != user.username):
                flash('系统账号不能更改用户名')
                return redirect(url_for('edit_user', user_id=user.id))
            if (user.username == 'tourist'
                    and (form.is_admin.data or form.is_sub_admin.data)):
                flash('游客账号不能被授予管理权限')
                return redirect(url_for('edit_user', user_id=user.id))
            if user.id == current_user.id and form.is_banned.data:
                flash('您不能封禁自己的账户')
                return redirect(url_for('edit_user', user_id=user.id))
            if (user.id == current_user.id and current_user.is_admin
                    and not form.is_admin.data):
                flash('您不能取消自己的管理员权限')
                return redirect(url_for('edit_user', user_id=user.id))

            # 记录修改内容
            changed_fields = []
            if user.username != form.username.data:
                changed_fields.append(f"用户名从 {user.username} 修改为 {form.username.data}")
            
            if user.email != form.email.data:
                changed_fields.append(f"邮箱从 {user.email} 修改为 {form.email.data}")
            
            # 只有管理员可以更改用户角色
            if current_user.is_admin:
                if user.is_admin != form.is_admin.data:
                    changed_fields.append(f"管理员权限: {'授予' if form.is_admin.data else '取消'}")
                
                if user.is_sub_admin != form.is_sub_admin.data:
                    changed_fields.append(f"子管理员权限: {'授予' if form.is_sub_admin.data else '取消'}")
            
            if user.is_banned != form.is_banned.data:
                changed_fields.append(f"封禁状态: {'封禁' if form.is_banned.data else '解除封禁'}")
            
            if form.password.data:
                changed_fields.append("修改了密码")
            
            # 保存修改
            user.username = form.username.data
            user.email = form.email.data
            
            # 只有管理员可以更改用户角色
            if current_user.is_admin:
                user.is_admin = form.is_admin.data
                user.is_sub_admin = form.is_sub_admin.data
            
            user.is_banned = form.is_banned.data
            user.banned_reason = form.banned_reason.data if form.is_banned.data else None
            
            # 更新密码
            if form.password.data:
                user.set_password(form.password.data)
            
            try:
                user.save()
            except sqlite3.IntegrityError:
                flash('用户名或邮箱已被使用')
                return redirect(url_for('edit_user', user_id=user.id))
            
            # 记录操作日志
            if changed_fields:
                description = f"修改了用户 {user.username} 的信息: " + ", ".join(changed_fields)
                ActivityLog.create_log(
                    user_id=current_user.id,
                    action='admin_edit_user',
                    target_type='user',
                    target_id=user.id,
                    description=description
                )
            
            flash(f'用户 {user.username} 信息已更新')
            return redirect(url_for('user_profile', username=user.username))
        elif request.method == 'GET':
            form.username.data = user.username
            form.email.data = user.email
            form.is_admin.data = user.is_admin
            form.is_sub_admin.data = user.is_sub_admin
            form.is_banned.data = user.is_banned
            form.banned_reason.data = user.banned_reason
        
        return render_template('admin/edit_user.html', title='编辑用户', form=form, user=user)
    
    # 封禁用户
    @app.route('/admin/user/<int:user_id>/ban', methods=['GET', 'POST'])
    @login_required
    def ban_user(user_id):
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限访问此页面')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        
        # 子管理员不能封禁管理员
        if current_user.is_sub_admin and user.is_admin:
            flash('您没有权限封禁管理员账户')
            return redirect(url_for('admin_users'))
        
        # 不能封禁自己
        if user.id == current_user.id:
            flash('您不能封禁自己的账户')
            return redirect(url_for('admin_users'))
        
        form = BanUserForm()
        if form.validate_on_submit():
            reason = form.reason.data
            user.ban(reason=reason)
            
            # 记录操作日志
            ActivityLog.create_log(
                user_id=current_user.id,
                action='user_ban',
                target_type='user',
                target_id=user.id,
                description=f'封禁了用户: {user.username}, 原因: {reason}'
            )
            
            flash(f'用户 {user.username} 已被封禁')
            return redirect(url_for('admin_users'))
        
        return render_template('admin/ban_user.html', title='封禁用户', form=form, user=user)
    
    # 解除封禁用户
    @app.route('/admin/user/<int:user_id>/unban', methods=['POST'])
    @login_required
    def unban_user(user_id):
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限访问此页面')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        if current_user.is_sub_admin and user.is_admin:
            abort(403)
        
        user.unban()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='user_unban',
            target_type='user',
            target_id=user.id,
            description=f'解除了用户: {user.username} 的封禁'
        )
        
        flash(f'用户 {user.username} 的封禁已解除')
        return redirect(url_for('user_profile', username=user.username))
    
    # 提升为子管理员
    @app.route('/admin/user/<int:user_id>/promote/<role>', methods=['POST'])
    @login_required
    def promote_user(user_id, role):
        if not current_user.is_admin:
            flash('只有管理员可以更改用户角色')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        if user.username == 'tourist':
            flash('游客账号不能被授予管理权限')
            return redirect(url_for('user_profile', username=user.username))
        
        if role not in {'admin', 'sub_admin'}:
            abort(404)

        if role == 'admin':
            user.promote_to_admin()
            
            # 记录操作日志
            ActivityLog.create_log(
                user_id=current_user.id,
                action='user_promote_admin',
                target_type='user',
                target_id=user.id,
                description=f'将用户: {user.username} 提升为管理员'
            )
            
            flash(f'用户 {user.username} 已被提升为管理员')
        elif role == 'sub_admin':
            user.promote_to_sub_admin()
            
            # 记录操作日志
            ActivityLog.create_log(
                user_id=current_user.id,
                action='user_promote_sub_admin',
                target_type='user',
                target_id=user.id,
                description=f'将用户: {user.username} 提升为子管理员'
            )
            
            flash(f'用户 {user.username} 已被提升为子管理员')
        
        return redirect(url_for('user_profile', username=user.username))
    
    # 取消管理员/子管理员角色
    @app.route('/admin/user/<int:user_id>/demote', methods=['POST'])
    @login_required
    def demote_user(user_id):
        if not current_user.is_admin:
            flash('只有管理员可以更改用户角色')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        if user.id == current_user.id:
            flash('您不能取消自己的管理员权限')
            return redirect(url_for('user_profile', username=user.username))
        
        if user.is_admin:
            user.demote_from_admin()
            
            # 记录操作日志
            ActivityLog.create_log(
                user_id=current_user.id,
                action='user_demote_admin',
                target_type='user',
                target_id=user.id,
                description=f'取消了用户: {user.username} 的管理员权限'
            )
            
            flash(f'用户 {user.username} 已被取消管理员权限')
        elif user.is_sub_admin:
            user.demote_from_sub_admin()
            
            # 记录操作日志
            ActivityLog.create_log(
                user_id=current_user.id,
                action='user_demote_sub_admin',
                target_type='user',
                target_id=user.id,
                description=f'取消了用户: {user.username} 的子管理员权限'
            )
            
            flash(f'用户 {user.username} 已被取消子管理员权限')
        
        return redirect(url_for('user_profile', username=user.username))
    
    # 创建新反馈
    @app.route('/create', methods=['GET', 'POST'])
    @login_required
    def create_post():
        # 检查游客是否可以发帖
        if current_user.username == 'tourist':
            allow_tourist = g.settings.get('allow_tourist', 'true')
            if allow_tourist != 'true':
                flash('管理员已禁止游客发帖，请使用注册账号')
                return redirect(url_for('index'))
                
        form = PostForm()
        if form.validate_on_submit():
            # 判断是否为游客发布
            is_tourist = current_user.username == 'tourist'
            
            post = Post(
                title=form.title.data,
                content=form.content.data,
                user_id=current_user.id,
                is_tourist_post=is_tourist,
                is_approved=None if is_tourist else True  # 游客帖子默认未审核状态
            )
            post.save()
            
            # 记录操作日志
            ActivityLog.create_log(
                user_id=current_user.id,
                action='post_create',
                target_type='post',
                target_id=post.id,
                description=f'发布了新反馈: {post.title}'
            )
            
            if is_tourist:
                flash('反馈已提交，等待管理员审核')
            else:
                flash('反馈已发布')
                
            return redirect(url_for('index'))
        return render_template('create_post.html', title='发布反馈', form=form)
    
    # 查看反馈
    @app.route('/post/<int:id>', methods=['GET', 'POST'])
    def post(id):
        post_data = Post.get_by_id(id)
        if not post_data:
            abort(404)

        is_moderator = current_user.is_admin or current_user.is_sub_admin
        if post_data.is_deleted and not is_moderator and current_user.id != post_data.user_id:
            abort(404)
        if (post_data.is_tourist_post and post_data.is_approved is not True
                and not is_moderator):
            abort(404)
        
        # 获取所有根评论（非回复的评论）
        # 保留删除占位，避免父评论删除后整条回复链消失。
        root_comments = Comment.get_comments_by_post_id(
            id, include_deleted=True,
            max_depth=app.config['MAX_COMMENT_DEPTH'],
        )
        
        # 获取所有已采纳的评论
        accepted_comments = Comment.get_all_accepted_comments_by_post_id(id)
        has_accepted_comment = any(comment.is_accepted for comment in accepted_comments)
            
        form = CommentForm()
        if form.validate_on_submit():
            if not current_user.is_authenticated:
                flash('请先登录再发表评论')
                return redirect(url_for('login', next=request.url))
            
            # 检查游客是否可以评论
            if current_user.username == 'tourist':
                allow_tourist = g.settings.get('allow_tourist', 'true')
                allow_tourist_comment = g.settings.get('allow_tourist_comment', 'true')
                
                if allow_tourist != 'true':
                    flash('管理员已禁止游客评论，请使用注册账号')
                    return redirect(url_for('post', id=id))
                
                if allow_tourist_comment != 'true':
                    flash('管理员已禁止游客评论，请使用注册账号')
                    return redirect(url_for('post', id=id))
                    
            if post_data.is_deleted:
                flash('该帖子已被删除，无法评论')
                return redirect(url_for('post', id=id))
            
            content = form.content.data
            parent_id = form.parent_id.data if form.parent_id.data else None
            
            if not content:
                flash('评论内容不能为空', 'error')
                return redirect(url_for('post', id=id))
            
            # 检查父评论是否存在
            if parent_id:
                parent_comment = Comment.get_by_id(parent_id)
                if (not parent_comment or parent_comment.post_id != post_data.id
                        or parent_comment.is_deleted):
                    flash('回复的评论不存在', 'error')
                    return redirect(url_for('post', id=id))
                if Comment.get_depth(parent_id) >= app.config['MAX_COMMENT_DEPTH']:
                    flash('回复层级已达上限', 'error')
                    return redirect(url_for('post', id=id))
            
            # 创建评论
            comment = Comment(
                content=content,
                user_id=current_user.id,
                post_id=post_data.id,
                parent_id=parent_id
            )
            comment.save()
            
            # 记录活动日志
            log_description = "发表了评论"
            if parent_id:
                parent_user = Comment.get_by_id(parent_id).user
                log_description = f"回复了 {parent_user.username} 的评论"
            
            activity = ActivityLog(
                user_id=current_user.id,
                action="create_comment",
                target_type="comment",
                target_id=comment.id,
                description=f"{current_user.username} {log_description}"
            )
            activity.save()
            
            flash('评论已发布', 'success')
            return redirect(url_for('post', id=id))
        
        return render_template(
            'post.html', post=post_data, root_comments=root_comments,
            accepted_comments=accepted_comments, form=form,
            has_accepted_comment=has_accepted_comment,
        )
    
    # 删除反馈
    @app.route('/post/<int:post_id>/delete', methods=['POST'])
    @login_required
    def delete_post(post_id):
        post = Post.get_by_id(post_id)
        if not post:
            abort(404)
        
        # 禁止游客删除反馈，即使是自己发布的
        if current_user.username == 'tourist' and not current_user.is_admin and not current_user.is_sub_admin:
            flash('游客账户不能删除反馈')
            return redirect(url_for('post', id=post_id))
            
        # 只有管理员或自己发布的内容可以删除
        if not current_user.is_admin and not current_user.is_sub_admin and current_user.id != post.user_id:
            abort(403)
        
        post.soft_delete(current_user.id)
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='post_delete',
            target_type='post',
            target_id=post.id,
            description=f'删除了反馈: {post.title}'
        )
        
        flash('反馈已删除')
        return redirect(url_for('index'))
    
    # 置顶反馈
    @app.route('/post/<int:post_id>/pin', methods=['POST'])
    @login_required
    def pin_post(post_id):
        # 只有管理员可以置顶反馈
        if not current_user.is_admin and not current_user.is_sub_admin:
            abort(403)
        
        post = Post.get_by_id(post_id)
        if not post:
            abort(404)
        
        post.pin()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='post_pin',
            target_type='post',
            target_id=post.id,
            description=f'置顶了反馈: {post.title}'
        )
        
        flash('反馈已置顶')
        return redirect(url_for('post', id=post_id))
    
    # 取消置顶反馈
    @app.route('/post/<int:post_id>/unpin', methods=['POST'])
    @login_required
    def unpin_post(post_id):
        # 只有管理员可以取消置顶反馈
        if not current_user.is_admin and not current_user.is_sub_admin:
            abort(403)
        
        post = Post.get_by_id(post_id)
        if not post:
            abort(404)
        
        post.unpin()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='post_unpin',
            target_type='post',
            target_id=post.id,
            description=f'取消置顶反馈: {post.title}'
        )
        
        flash('已取消置顶')
        return redirect(url_for('post', id=post_id))
    
    # 恢复已删除的反馈
    @app.route('/post/<int:post_id>/restore', methods=['POST'])
    @login_required
    def restore_post(post_id):
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('只有管理员可以恢复已删除的反馈')
            return redirect(url_for('index'))
        
        post = Post.get_by_id(post_id)
        if not post:
            abort(404)
        
        if not post.is_deleted:
            flash('该反馈未被删除')
            return redirect(url_for('post', id=post.id))
        
        post.restore()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='post_restore',
            target_type='post',
            target_id=post.id,
            description=f'恢复了反馈: {post.title}'
        )
        
        flash('反馈已恢复')
        return redirect(url_for('post', id=post.id))
    
    # 删除评论（软删除）
    @app.route('/comment/<int:id>/delete', methods=['POST'])
    @login_required
    def delete_comment(id):
        comment = Comment.get_by_id(id)
        if not comment:
            abort(404)
        
        # 禁止游客删除评论，即使是自己发布的
        if current_user.username == 'tourist' and not current_user.is_admin and not current_user.is_sub_admin:
            flash('游客账户不能删除评论')
            return redirect(url_for('post', id=comment.post_id))
            
        # 检查权限：只有发布者、管理员和子管理员可以删除
        if comment.user_id != current_user.id and not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限删除此评论')
            return redirect(url_for('post', id=comment.post_id))
        
        comment.soft_delete(current_user.id)
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='comment_delete',
            target_type='comment',
            target_id=comment.id,
            description=f'删除了评论: {comment.content[:30]}...'
        )
        
        flash('评论已删除')
        return redirect(url_for('post', id=comment.post_id))
    
    # 恢复已删除的评论
    @app.route('/comment/<int:id>/restore', methods=['POST'])
    @login_required
    def restore_comment(id):
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('只有管理员可以恢复已删除的评论')
            return redirect(url_for('index'))
        
        comment = Comment.get_by_id(id)
        if not comment:
            abort(404)
        
        if not comment.is_deleted:
            flash('该评论未被删除')
            return redirect(url_for('post', id=comment.post_id))
        
        comment.restore()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='comment_restore',
            target_type='comment',
            target_id=comment.id,
            description=f'恢复了评论: {comment.content[:30]}...'
        )
        
        flash('评论已恢复')
        return redirect(url_for('post', id=comment.post_id))
    
    # 采纳评论
    @app.route('/comment/<int:id>/accept', methods=['POST'])
    @login_required
    def accept_comment(id):
        """采纳评论"""
        # 游客不能采纳评论
        if current_user.username == 'tourist':
            flash('游客用户无法采纳评论', 'error')
            return redirect(url_for('index'))
        
        # 获取评论
        comment = Comment.get_by_id(id)
        if not comment:
            flash('评论不存在', 'error')
            return redirect(url_for('index'))
        
        # 如果评论已删除，不能采纳
        if comment.is_deleted:
            flash('已删除的评论不能被采纳', 'error')
            return redirect(url_for('post', id=comment.post_id))
        
        # 获取评论所属帖子
        post = Post.get_by_id(comment.post_id)
        if not post:
            flash('帖子不存在', 'error')
            return redirect(url_for('index'))
        
        can_moderate = current_user.is_admin or current_user.is_sub_admin
        if not can_moderate and current_user.id != post.user_id:
            abort(403)

        # 管理员可以采纳自己的评论，普通帖子作者不能采纳自己的评论
        if current_user.id != comment.user_id or can_moderate:
            # 采纳评论
            comment.accept(current_user.id)
            
            # 记录活动日志
            activity = ActivityLog(
                user_id=current_user.id,
                action="accept_comment",
                target_type="comment",
                target_id=comment.id,
                description=f"{current_user.username} 采纳了 {comment.user.username} 的评论"
            )
            activity.save()
            
            flash('已采纳评论', 'success')
        else:
            flash('您不能采纳自己的评论', 'error')
        
        return redirect(url_for('post', id=post.id))
    
    # 取消采纳评论
    @app.route('/comment/<int:id>/cancel-accept', methods=['POST'])
    @login_required
    def cancel_accept_comment(id):
        # 获取评论
        comment = Comment.get_by_id(id)
        if not comment:
            abort(404)
        
        # 检查评论是否已被采纳
        if not comment.is_accepted:
            flash('该评论未被采纳')
            return redirect(url_for('post', id=comment.post_id))
        
        # 获取帖子
        post = Post.get_by_id(comment.post_id)
        if not post:
            abort(404)
        
        # 游客不能取消采纳
        if current_user.username == 'tourist':
            flash('游客账户不能取消采纳评论')
            return redirect(url_for('post', id=post.id))
        
        # 权限检查：
        # 1. 如果是管理员，可以取消采纳任何评论
        # 2. 如果是帖子作者，可以取消采纳任何评论
        if current_user.is_admin or current_user.is_sub_admin or current_user.id == post.user_id:
            # 有权取消采纳
            pass
        else:
            # 其他用户无权取消采纳
            flash('只有帖子作者或管理员可以取消采纳')
            return redirect(url_for('post', id=post.id))
        
        # 取消采纳
        comment.cancel_accept()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='comment_cancel_accept',
            target_type='comment',
            target_id=comment.id,
            description=f'取消采纳评论: {comment.content[:30]}...'
        )
        
        flash('已取消采纳评论')
        return redirect(url_for('post', id=post.id))
    
    # 审核通过游客帖子
    @app.route('/post/<int:post_id>/approve', methods=['POST'])
    @login_required
    def approve_post(post_id):
        # 只有管理员可以审核帖子
        if not current_user.is_admin and not current_user.is_sub_admin:
            abort(403)
        
        post = Post.get_by_id(post_id)
        if not post:
            abort(404)
        
        if not post.is_tourist_post:
            flash('只有游客发布的帖子需要审核')
            return redirect(url_for('post', id=post_id))
        if post.is_deleted:
            flash('已删除的帖子不能通过审核，请先恢复')
            return redirect(url_for('admin_pending_posts', show_deleted=1))
        
        post.approve()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='post_approve',
            target_type='post',
            target_id=post.id,
            description=f'审核通过反馈: {post.title}'
        )
        
        flash('帖子已审核通过')
        return redirect(url_for('post', id=post_id))
    
    # 拒绝游客帖子
    @app.route('/post/<int:post_id>/reject', methods=['POST'])
    @login_required
    def reject_post(post_id):
        # 只有管理员可以拒绝帖子
        if not current_user.is_admin and not current_user.is_sub_admin:
            abort(403)
        
        post = Post.get_by_id(post_id)
        if not post:
            abort(404)
        
        if not post.is_tourist_post:
            flash('只有游客发布的帖子需要审核')
            return redirect(url_for('post', id=post_id))
        if post.is_deleted:
            flash('已删除的帖子不能执行审核操作')
            return redirect(url_for('admin_pending_posts', show_deleted=1))
        
        post.reject()
        
        # 记录操作日志
        ActivityLog.create_log(
            user_id=current_user.id,
            action='post_reject',
            target_type='post',
            target_id=post.id,
            description=f'拒绝了反馈: {post.title}'
        )
        
        flash('已拒绝该帖子')
        return redirect(url_for('post', id=post_id))
    
    # 管理员 - 待审核帖子列表
    @app.route('/admin/pending-posts')
    @login_required
    def admin_pending_posts():
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限访问此页面')
            return redirect(url_for('index'))
        
        page = max(1, request.args.get('page', 1, type=int))
        show_deleted = request.args.get('show_deleted', 0, type=int)
        view = request.args.get('status', 'deleted' if show_deleted else 'pending')
        if view not in {'pending', 'rejected', 'deleted'}:
            abort(400)
        show_deleted = view == 'deleted'
        
        conn = get_db_connection()
        
        if view == 'deleted':
            # 获取已删除的帖子总数
            total = conn.execute('SELECT COUNT(*) FROM post WHERE is_deleted = 1').fetchone()[0]
            page = clamp_page(page, total, app.config['POSTS_PER_PAGE'])
            # 获取分页数据
            offset = (page - 1) * app.config['POSTS_PER_PAGE']
            posts_data = conn.execute(
                'SELECT * FROM post WHERE is_deleted = 1 ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (app.config['POSTS_PER_PAGE'], offset)
            ).fetchall()
            
            title = '已删除反馈'
        elif view == 'rejected':
            total = conn.execute(
                'SELECT COUNT(*) FROM post WHERE is_tourist_post = 1 AND is_approved = 0 AND is_deleted = 0'
            ).fetchone()[0]
            page = clamp_page(page, total, app.config['POSTS_PER_PAGE'])
            offset = (page - 1) * app.config['POSTS_PER_PAGE']
            posts_data = conn.execute(
                '''SELECT * FROM post
                   WHERE is_tourist_post = 1 AND is_approved = 0 AND is_deleted = 0
                   ORDER BY created_at DESC LIMIT ? OFFSET ?''',
                (app.config['POSTS_PER_PAGE'], offset)
            ).fetchall()
            title = '已拒绝反馈'
        else:
            # 获取待审核帖子总数
            total = conn.execute('SELECT COUNT(*) FROM post WHERE is_tourist_post = 1 AND is_approved IS NULL AND is_deleted = 0').fetchone()[0]
            page = clamp_page(page, total, app.config['POSTS_PER_PAGE'])
            # 获取分页数据
            offset = (page - 1) * app.config['POSTS_PER_PAGE']
            posts_data = conn.execute(
                'SELECT * FROM post WHERE is_tourist_post = 1 AND is_approved IS NULL AND is_deleted = 0 ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (app.config['POSTS_PER_PAGE'], offset)
            ).fetchall()
            
            title = '待审核反馈'
        
        # 处理帖子数据
        posts = []
        for post_data in posts_data:
            post = Post(
                id=post_data['id'],
                title=post_data['title'],
                content=post_data['content'],
                created_at=post_data['created_at'],
                user_id=post_data['user_id'],
                is_deleted=bool(post_data['is_deleted']) if 'is_deleted' in post_data.keys() else False,
                deleted_at=post_data['deleted_at'] if 'deleted_at' in post_data.keys() else None,
                deleted_by=post_data['deleted_by'] if 'deleted_by' in post_data.keys() else None,
                is_pinned=bool(post_data['is_pinned']) if 'is_pinned' in post_data.keys() else False,
                is_tourist_post=bool(post_data['is_tourist_post']) if 'is_tourist_post' in post_data.keys() else False,
                is_approved=nullable_bool(post_data['is_approved']) if 'is_approved' in post_data.keys() else None
            )
            posts.append(post)
        
        # 创建分页对象
        Post.preload(posts)
        posts = Pagination(page, app.config['POSTS_PER_PAGE'], total, posts)
        conn.close()
        
        return render_template(
            'admin/pending_posts.html', title=title, posts=posts,
            show_deleted=show_deleted, view=view
        )
    
    # 管理员控制台
    @app.route('/admin/dashboard')
    @login_required
    def admin_dashboard():
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有访问管理员面板的权限')
            return redirect(url_for('index'))
        
        conn = get_db_connection()
        
        # 用户统计
        user_count = conn.execute('SELECT COUNT(*) FROM user').fetchone()[0]
        admin_count = conn.execute('SELECT COUNT(*) FROM user WHERE is_admin = 1').fetchone()[0]
        sub_admin_count = conn.execute('SELECT COUNT(*) FROM user WHERE is_sub_admin = 1').fetchone()[0]
        regular_user_count = conn.execute(
            'SELECT COUNT(*) FROM user WHERE is_admin = 0 AND is_sub_admin = 0'
        ).fetchone()[0]
        
        # 按平台时区统计当天新增数据
        timezone_name = g.settings.get('timezone', 'Asia/Shanghai')
        try:
            target_timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError:
            target_timezone = pytz.timezone('Asia/Shanghai')
        local_date = datetime.now(dt_timezone.utc).astimezone(target_timezone).date()
        next_date = local_date + timedelta(days=1)
        start_utc = target_timezone.localize(
            datetime.combine(local_date, datetime.min.time())
        ).astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        end_utc = target_timezone.localize(
            datetime.combine(next_date, datetime.min.time())
        ).astimezone(dt_timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        today_new_users = conn.execute(
            'SELECT COUNT(*) FROM user WHERE created_at >= ? AND created_at < ?',
            (start_utc, end_utc)
        ).fetchone()[0]
        
        # 帖子统计
        post_count = conn.execute('SELECT COUNT(*) FROM post').fetchone()[0]
        pending_count = conn.execute('SELECT COUNT(*) FROM post WHERE is_tourist_post = 1 AND is_approved IS NULL AND is_deleted = 0').fetchone()[0]
        deleted_count = conn.execute('SELECT COUNT(*) FROM post WHERE is_deleted = 1').fetchone()[0]
        pinned_count = conn.execute('SELECT COUNT(*) FROM post WHERE is_pinned = 1').fetchone()[0]
        
        # 新增帖子
        today_new_posts = conn.execute(
            'SELECT COUNT(*) FROM post WHERE created_at >= ? AND created_at < ?',
            (start_utc, end_utc)
        ).fetchone()[0]
        
        # 计算百分比
        pending_percent = round((pending_count / post_count) * 100) if post_count > 0 else 0
        
        # 获取活动日志
        recent_activities = ActivityLog.get_recent_logs(10)
        
        platform_name = g.settings.get('platform_name', '反馈平台')
        allow_tourist = g.settings.get('allow_tourist', 'true')
        allow_tourist_comment = g.settings.get('allow_tourist_comment', 'true')
        
        conn.close()
        
        return render_template('admin/dashboard.html', 
                              title='管理员面板', 
                              user_count=user_count,
                              admin_count=admin_count,
                              sub_admin_count=sub_admin_count,
                              regular_user_count=regular_user_count,
                              today_new_users=today_new_users,
                              post_count=post_count,
                              pending_count=pending_count,
                              deleted_count=deleted_count,
                              pinned_count=pinned_count,
                              today_new_posts=today_new_posts,
                              pending_percent=pending_percent,
                              recent_activities=recent_activities,
                              platform_name=platform_name,
                              allow_tourist=allow_tourist,
                              allow_tourist_comment=allow_tourist_comment)
    
    # 系统设置
    @app.route('/admin/settings', methods=['GET', 'POST'])
    @login_required
    def admin_settings():
        if not current_user.is_admin:
            flash('只有管理员可以修改系统设置')
            return redirect(url_for('admin_dashboard'))

        if request.method == 'POST':
            platform_name = request.form.get('platform_name', '').strip()
            if not platform_name or len(platform_name) > 80:
                flash('平台名称长度必须在 1 到 80 个字符之间')
                return redirect(url_for('admin_settings'))
            allow_tourist = 'true' if request.form.get('allow_tourist') else 'false'
            allow_tourist_comment = 'true' if request.form.get('allow_tourist_comment') else 'false'
            timezone_setting = request.form.get('timezone', 'Asia/Shanghai')
            if timezone_setting not in pytz.all_timezones_set:
                flash('无效的时区设置')
                return redirect(url_for('admin_settings'))

            Settings.set_many({
                'platform_name': (platform_name, '平台名称，显示在页面顶部和标题中'),
                'allow_tourist': (allow_tourist, '是否允许游客登录和发帖'),
                'allow_tourist_comment': (allow_tourist_comment, '是否允许游客评论帖子'),
                'timezone': (timezone_setting, '系统时区设置'),
            })

            # 记录活动
            ActivityLog.create_log(
                user_id=current_user.id,
                action='update',
                target_type='settings',
                target_id=0,
                description=f'管理员 {current_user.username} 更新了系统设置'
            )

            flash('系统设置已更新')
            return redirect(url_for('admin_dashboard'))
        
        platform_name = g.settings.get('platform_name', '反馈平台')
        allow_tourist = g.settings.get('allow_tourist', 'true')
        allow_tourist_comment = g.settings.get('allow_tourist_comment', 'true')
        timezone_setting = g.settings.get('timezone', 'Asia/Shanghai')
        return render_template('admin/settings.html',
                              title='系统设置',
                              platform_name=platform_name,
                              allow_tourist=allow_tourist,
                              allow_tourist_comment=allow_tourist_comment,
                              timezone_setting=timezone_setting)

    # 数据库导出
    @app.route('/admin/export-database', methods=['POST'])
    @login_required
    def export_database():
        if not current_user.is_admin:
            flash('只有管理员可以导出数据库')
            return redirect(url_for('admin_dashboard'))

        backup_path = None
        try:
            from models import DB_PATH

            # 检查数据库文件是否存在
            if not os.path.exists(DB_PATH):
                flash('数据库文件不存在')
                return redirect(url_for('admin_settings'))

            # 生成带时间戳的文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'feedback_backup_{timestamp}.db'

            # 记录操作日志
            ActivityLog.create_log(
                user_id=current_user.id,
                action='database_export',
                target_type='system',
                target_id=0,
                description=f'管理员 {current_user.username} 导出了数据库'
            )

            backup = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
            backup_path = backup.name
            backup.close()
            source = sqlite3.connect(DB_PATH)
            destination = sqlite3.connect(backup_path)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()

            response = send_file(
                backup_path, as_attachment=True, download_name=filename
            )

            @response.call_on_close
            def remove_backup():
                try:
                    os.remove(backup_path)
                except OSError:
                    app.logger.warning('无法删除临时数据库备份 %s', backup_path)

            return response

        except (OSError, sqlite3.Error):
            app.logger.exception('导出数据库失败')
            if backup_path:
                try:
                    os.remove(backup_path)
                except OSError:
                    pass
            flash('导出数据库时发生错误，请稍后重试')
            return redirect(url_for('admin_settings'))

    # 错误处理
    @app.errorhandler(400)
    def bad_request_error(error):
        return render_template('400.html'), 400

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('500.html'), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(
        host=os.environ.get('FLASK_HOST', '127.0.0.1'),
        port=int(os.environ.get('PORT', '5000')),
        debug=os.environ.get('FLASK_DEBUG') == '1',
    )
