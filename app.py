from flask import Flask, render_template, flash, redirect, url_for, request, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.urls import url_parse
from config import Config
from models import User, Post, Comment, init_db, get_db_connection
from forms import LoginForm, RegisterForm, PostForm, CommentForm, EditProfileForm, AdminEditProfileForm, BanUserForm
import os
import re

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 添加nl2br过滤器
    @app.template_filter('nl2br')
    def nl2br_filter(s):
        if s:
            return s.replace('\n', '<br>')
        return s
    
    # 添加日期格式化过滤器
    @app.template_filter('format_datetime')
    def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
        if value is None:
            return ''
        if isinstance(value, str):
            try:
                from datetime import datetime
                # 尝试将字符串解析为datetime
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                # 如果无法解析，直接返回字符串
                return value
        try:
            return value.strftime(format)
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
        return User.get_by_id(int(id))
    
    # 创建管理员账户（如果不存在）
    admin = User.get_by_username('admin')
    if not admin:
        admin = User(username='admin', email='admin@example.com', is_admin=True)
        admin.set_password('admin123')
        admin.save()
    
    # 每次请求前更新用户最后活跃时间
    @app.before_request
    def before_request():
        if current_user.is_authenticated:
            current_user.update_last_seen()
            # 如果用户被封禁，强制登出
            if current_user.is_banned and request.endpoint not in ['logout', 'static']:
                flash('您的账号已被封禁，无法继续使用。如有疑问，请联系管理员。')
                logout_user()
                return redirect(url_for('login'))
        # 检查用户登录状态
        if not current_user.is_authenticated and request.endpoint not in ['login', 'register', 'static', 'logout'] and not request.path.startswith('/static/'):
            flash('请先登录再访问此页面')
            return redirect(url_for('login', next=request.full_path))
    
    # 首页 - 显示所有反馈
    @app.route('/')
    @app.route('/index')
    def index():
        page = request.args.get('page', 1, type=int)
        include_deleted = False
        if current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin):
            include_deleted = request.args.get('include_deleted', 'false').lower() == 'true'
        posts = Post.get_all(page=page, per_page=app.config['POSTS_PER_PAGE'], include_deleted=include_deleted)
        return render_template('index.html', title='反馈广场', posts=posts, include_deleted=include_deleted)
    
    # 登录
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
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
            if not next_page or url_parse(next_page).netloc != '':
                next_page = url_for('index')
            flash(f'欢迎, {user.username}!')
            return redirect(next_page)
        return render_template('login.html', title='登录', form=form)
    
    # 注册
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        form = RegisterForm()
        if form.validate_on_submit():
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            user.save()
            flash('注册成功，现在可以登录了!')
            return redirect(url_for('login'))
        return render_template('register.html', title='注册', form=form)
    
    # 注销
    @app.route('/logout')
    def logout():
        logout_user()
        flash('已成功注销')
        return redirect(url_for('index'))
    
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
                'SELECT * FROM post WHERE user_id = ? AND (is_deleted = 0 OR is_deleted IS NULL) ORDER BY is_pinned DESC, created_at DESC',
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
                'SELECT c.*, p.title as post_title FROM comment c JOIN post p ON c.post_id = p.id WHERE c.user_id = ? AND (c.is_deleted = 0 OR c.is_deleted IS NULL) ORDER BY c.created_at DESC',
                (user.id,)
            ).fetchall()
        
        result_comments = []
        for comment in user_comments:
            result_comments.append(Comment(
                id=comment['id'],
                content=comment['content'],
                created_at=comment['created_at'],
                user_id=comment['user_id'],
                post_id=comment['post_id'],
                is_deleted=bool(comment['is_deleted']) if 'is_deleted' in comment.keys() else False,
                deleted_at=comment['deleted_at'] if 'deleted_at' in comment.keys() else None,
                deleted_by=comment['deleted_by'] if 'deleted_by' in comment.keys() else None
            ))
        
        conn.close()
        
        return render_template('user_profile.html', user=user, user_posts=result_posts, user_comments=result_comments)
    
    # 编辑个人信息
    @app.route('/edit-profile', methods=['GET', 'POST'])
    @login_required
    def edit_profile():
        form = EditProfileForm(current_user.username, current_user.email)
        if form.validate_on_submit():
            # 验证当前密码
            if form.current_password.data and not current_user.check_password(form.current_password.data):
                flash('当前密码不正确')
                return redirect(url_for('edit_profile'))
            
            current_user.username = form.username.data
            current_user.email = form.email.data
            
            # 更新密码
            if form.password.data:
                current_user.set_password(form.password.data)
            
            current_user.save()
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
        
        page = request.args.get('page', 1, type=int)
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
            
            user.save()
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
            user.ban(reason=form.reason.data)
            flash(f'用户 {user.username} 已被封禁')
            return redirect(url_for('admin_users'))
        
        return render_template('admin/ban_user.html', title='封禁用户', form=form, user=user)
    
    # 解除封禁用户
    @app.route('/admin/user/<int:user_id>/unban')
    @login_required
    def unban_user(user_id):
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限访问此页面')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        
        user.unban()
        flash(f'用户 {user.username} 的封禁已解除')
        return redirect(url_for('user_profile', username=user.username))
    
    # 提升为子管理员
    @app.route('/admin/user/<int:user_id>/promote/<role>')
    @login_required
    def promote_user(user_id, role):
        if not current_user.is_admin:
            flash('只有管理员可以更改用户角色')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        
        if role == 'admin':
            user.promote_to_admin()
            flash(f'用户 {user.username} 已被提升为管理员')
        elif role == 'sub_admin':
            user.promote_to_sub_admin()
            flash(f'用户 {user.username} 已被提升为子管理员')
        
        return redirect(url_for('user_profile', username=user.username))
    
    # 取消管理员/子管理员角色
    @app.route('/admin/user/<int:user_id>/demote')
    @login_required
    def demote_user(user_id):
        if not current_user.is_admin:
            flash('只有管理员可以更改用户角色')
            return redirect(url_for('index'))
        
        user = User.get_by_id(user_id)
        if not user:
            abort(404)
        
        if user.is_admin:
            user.demote_from_admin()
            flash(f'用户 {user.username} 已被取消管理员权限')
        elif user.is_sub_admin:
            user.demote_from_sub_admin()
            flash(f'用户 {user.username} 已被取消子管理员权限')
        
        return redirect(url_for('user_profile', username=user.username))
    
    # 创建新反馈
    @app.route('/create', methods=['GET', 'POST'])
    @login_required
    def create_post():
        if current_user.is_banned:
            flash('您的账号已被封禁，无法发布反馈')
            return redirect(url_for('index'))
        
        form = PostForm()
        if form.validate_on_submit():
            post = Post(
                title=form.title.data,
                content=form.content.data,
                user_id=current_user.id
            )
            post.save()
            flash('反馈已发布')
            return redirect(url_for('index'))
        return render_template('create_post.html', title='发布反馈', form=form)
    
    # 查看反馈
    @app.route('/post/<int:id>', methods=['GET', 'POST'])
    def post(id):
        post = Post.get_by_id(id)
        if not post:
            abort(404)
        
        # 非管理员不能查看已删除内容
        if post.is_deleted and not (current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin)):
            flash('该反馈已被删除')
            return redirect(url_for('index'))
        
        # 获取评论，管理员可以看到已删除的评论
        conn = get_db_connection()
        if current_user.is_authenticated and (current_user.is_admin or current_user.is_sub_admin):
            comments_db = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? ORDER BY created_at',
                (post.id,)
            ).fetchall()
        else:
            comments_db = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? AND (is_deleted = 0 OR is_deleted IS NULL) ORDER BY created_at',
                (post.id,)
            ).fetchall()
        
        comments = []
        for comment in comments_db:
            comments.append(Comment(
                id=comment['id'],
                content=comment['content'],
                created_at=comment['created_at'],
                user_id=comment['user_id'],
                post_id=comment['post_id'],
                is_deleted=bool(comment['is_deleted']) if 'is_deleted' in comment.keys() else False,
                deleted_at=comment['deleted_at'] if 'deleted_at' in comment.keys() else None,
                deleted_by=comment['deleted_by'] if 'deleted_by' in comment.keys() else None
            ))
        
        conn.close()
        
        form = CommentForm()
        if form.validate_on_submit():
            if not current_user.is_authenticated:
                flash('请先登录后再评论')
                return redirect(url_for('login', next=request.url))
            
            if current_user.is_banned:
                flash('您的账号已被封禁，无法发表评论')
                return redirect(url_for('post', id=post.id))
            
            if post.is_deleted:
                flash('该反馈已被删除，无法添加新评论')
                return redirect(url_for('post', id=post.id))
            
            comment = Comment(
                content=form.content.data,
                user_id=current_user.id,
                post_id=post.id
            )
            comment.save()
            flash('评论已发表')
            return redirect(url_for('post', id=post.id))
        
        return render_template('post.html', title=post.title, post=post, comments=comments, form=form)
    
    # 删除反馈
    @app.route('/post/<int:post_id>/delete', methods=['POST'])
    @login_required
    def delete_post(post_id):
        post = Post.get_by_id(post_id)
        if not post:
            abort(404)
        
        # 只有管理员或自己发布的内容可以删除
        if not current_user.is_admin and not current_user.is_sub_admin and current_user.id != post.user_id:
            abort(403)
        
        post.soft_delete(current_user.id)
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
        flash('已取消置顶')
        return redirect(url_for('post', id=post_id))
    
    # 恢复已删除的反馈
    @app.route('/post/<int:post_id>/restore')
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
        flash('反馈已恢复')
        return redirect(url_for('post', id=post.id))
    
    # 删除评论（软删除）
    @app.route('/comment/<int:id>/delete')
    @login_required
    def delete_comment(id):
        conn = get_db_connection()
        comment_db = conn.execute('SELECT * FROM comment WHERE id = ?', (id,)).fetchone()
        conn.close()
        
        if not comment_db:
            abort(404)
        
        comment = Comment(
            id=comment_db['id'],
            content=comment_db['content'],
            created_at=comment_db['created_at'],
            user_id=comment_db['user_id'],
            post_id=comment_db['post_id']
        )
        
        # 检查权限：只有发布者、管理员和子管理员可以删除
        if comment.user_id != current_user.id and not current_user.is_admin and not current_user.is_sub_admin:
            flash('您没有权限删除此评论')
            return redirect(url_for('post', id=comment.post_id))
        
        comment.soft_delete(current_user.id)
        flash('评论已删除')
        return redirect(url_for('post', id=comment.post_id))
    
    # 恢复已删除的评论
    @app.route('/comment/<int:id>/restore')
    @login_required
    def restore_comment(id):
        if not current_user.is_admin and not current_user.is_sub_admin:
            flash('只有管理员可以恢复已删除的评论')
            return redirect(url_for('index'))
        
        conn = get_db_connection()
        comment_db = conn.execute('SELECT * FROM comment WHERE id = ?', (id,)).fetchone()
        conn.close()
        
        if not comment_db:
            abort(404)
        
        comment = Comment(
            id=comment_db['id'],
            content=comment_db['content'],
            created_at=comment_db['created_at'],
            user_id=comment_db['user_id'],
            post_id=comment_db['post_id'],
            is_deleted=bool(comment_db['is_deleted']) if 'is_deleted' in comment_db.keys() else False,
            deleted_at=comment_db['deleted_at'] if 'deleted_at' in comment_db.keys() else None,
            deleted_by=comment_db['deleted_by'] if 'deleted_by' in comment_db.keys() else None
        )
        
        if not comment.is_deleted:
            flash('该评论未被删除')
            return redirect(url_for('post', id=comment.post_id))
        
        comment.restore()
        flash('评论已恢复')
        return redirect(url_for('post', id=comment.post_id))
    
    # 错误处理
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('500.html'), 500
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True) 