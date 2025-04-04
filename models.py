import sqlite3
import click
from flask import current_app, g, url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import math
import os

# 数据库路径设置
db_dir = os.environ.get('DB_DIR', os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(db_dir, 'feedback.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT,
        email TEXT UNIQUE,
        is_admin BOOLEAN NOT NULL DEFAULT 0,
        is_sub_admin BOOLEAN NOT NULL DEFAULT 0,
        is_banned BOOLEAN NOT NULL DEFAULT 0,
        banned_reason TEXT,
        last_seen TIMESTAMP,
        posts INTEGER NOT NULL DEFAULT 0,
        comments INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 检查并添加缺少的列
    columns = {column[1] for column in cursor.execute("PRAGMA table_info(user)").fetchall()}
    if 'banned_reason' not in columns:
        cursor.execute('ALTER TABLE user ADD COLUMN banned_reason TEXT')
    if 'last_seen' not in columns:
        cursor.execute('ALTER TABLE user ADD COLUMN last_seen TIMESTAMP')
    if 'is_sub_admin' not in columns:
        cursor.execute('ALTER TABLE user ADD COLUMN is_sub_admin BOOLEAN NOT NULL DEFAULT 0')
    
    # 重新创建评论表以包含新的字段
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS comment_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT 0,
        deleted_at TIMESTAMP,
        deleted_by INTEGER,
        parent_id INTEGER,
        is_accepted BOOLEAN NOT NULL DEFAULT 0,
        accepted_by INTEGER,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id),
        FOREIGN KEY (post_id) REFERENCES post (id),
        FOREIGN KEY (parent_id) REFERENCES comment (id),
        FOREIGN KEY (deleted_by) REFERENCES user (id),
        FOREIGN KEY (accepted_by) REFERENCES user (id)
    )
    ''')
    
    # 检查旧表是否存在，如果存在则迁移数据
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='comment'")
    if cursor.fetchone():
        # 获取旧表的列信息
        old_columns = []
        for column in cursor.execute("PRAGMA table_info(comment)").fetchall():
            old_columns.append(column[1])
        
        # 准备INSERT语句
        common_columns = ['id', 'content', 'user_id', 'post_id', 'created_at']
        if 'is_deleted' in old_columns:
            common_columns.append('is_deleted')
        if 'deleted_at' in old_columns:
            common_columns.append('deleted_at')
        if 'deleted_by' in old_columns:
            common_columns.append('deleted_by')
        if 'parent_id' in old_columns:
            common_columns.append('parent_id')
        if 'is_accepted' in old_columns:
            common_columns.append('is_accepted')
        if 'accepted_by' in old_columns:
            common_columns.append('accepted_by')
        
        # 构建迁移SQL
        columns_str = ", ".join(common_columns)
        sql = f"INSERT INTO comment_new ({columns_str}) SELECT {columns_str} FROM comment"
        cursor.execute(sql)
        
        cursor.execute('DROP TABLE comment')
    
    cursor.execute('ALTER TABLE comment_new RENAME TO comment')
    
    # 帖子表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS post (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT 0,
        deleted_by INTEGER,
        deleted_at TIMESTAMP,
        is_pinned BOOLEAN NOT NULL DEFAULT 0,
        is_tourist_post BOOLEAN NOT NULL DEFAULT 0,
        is_approved BOOLEAN,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id),
        FOREIGN KEY (deleted_by) REFERENCES user (id)
    )
    ''')
    
    # 活动日志表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES user (id)
    )
    ''')
    
    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_user_id ON post (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_is_deleted ON post (is_deleted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_is_pinned ON post (is_pinned)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_is_tourist_post ON post (is_tourist_post)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_is_approved ON post (is_approved)')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_user_id ON comment (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_post_id ON comment (post_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_is_deleted ON comment (is_deleted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_parent_id ON comment (parent_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_is_accepted ON comment (is_accepted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_accepted_by ON comment (accepted_by)')
    
    # 创建设置表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value TEXT,
        description TEXT,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 初始化管理员账号
    cursor.execute('SELECT * FROM user WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        # 默认密码为 admin
        hashed_password = generate_password_hash('admin')
        cursor.execute('INSERT INTO user (username, password, is_admin) VALUES (?, ?, ?)',
                     ('admin', hashed_password, 1))
    
    conn.commit()
    conn.close()

# 辅助函数 - 将字符串转换为datetime对象
def parse_datetime(datetime_str):
    if datetime_str is None:
        return None
    
    if isinstance(datetime_str, datetime):
        return datetime_str
        
    try:
        return datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        try:
            return datetime.fromisoformat(datetime_str)
        except (ValueError, TypeError):
            return datetime.now()  # 无法解析时返回当前时间

class User(UserMixin):
    def __init__(self, id=None, username=None, email=None, password_hash=None, created_at=None, 
                 is_admin=False, is_sub_admin=False, is_banned=False, banned_reason=None, last_seen=None):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.created_at = created_at
        self.is_admin = is_admin
        self.is_sub_admin = is_sub_admin
        self.is_banned = is_banned
        self.banned_reason = banned_reason
        self.last_seen = last_seen
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def save(self):
        conn = get_db_connection()
        
        if self.id is None:
            # 创建新用户
            conn.execute(
                'INSERT INTO user (username, email, password, is_admin, is_sub_admin, is_banned, banned_reason) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (self.username, self.email, self.password_hash, int(self.is_admin), int(self.is_sub_admin), int(self.is_banned), self.banned_reason)
            )
            self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        else:
            # 更新现有用户
            conn.execute(
                'UPDATE user SET username = ?, email = ?, password = ?, is_admin = ?, is_sub_admin = ?, is_banned = ?, banned_reason = ? WHERE id = ?',
                (self.username, self.email, self.password_hash, int(self.is_admin), int(self.is_sub_admin), int(self.is_banned), self.banned_reason, self.id)
            )
        
        conn.commit()
        conn.close()
        return self
    
    def ban(self, reason=None):
        self.is_banned = True
        self.banned_reason = reason
        self.save()
        return self
    
    def unban(self):
        self.is_banned = False
        self.banned_reason = None
        self.save()
        return self
    
    def promote_to_admin(self):
        self.is_admin = True
        self.is_sub_admin = False  # 管理员自动覆盖子管理员
        self.save()
        return self
    
    def promote_to_sub_admin(self):
        if not self.is_admin:  # 只有非管理员可以成为子管理员
            self.is_sub_admin = True
            self.save()
        return self
    
    def demote_from_admin(self):
        self.is_admin = False
        self.save()
        return self
    
    def demote_from_sub_admin(self):
        self.is_sub_admin = False
        self.save()
        return self
    
    def update_last_seen(self):
        """更新用户最后活跃时间"""
        conn = get_db_connection()
        
        # 检查是否存在 last_seen 列
        columns = conn.execute('PRAGMA table_info(user)').fetchall()
        has_last_seen = any(column[1] == 'last_seen' for column in columns)
        
        # 如果不存在 last_seen 列，则添加它
        if not has_last_seen:
            try:
                conn.execute('ALTER TABLE user ADD COLUMN last_seen TIMESTAMP')
                conn.commit()
            except sqlite3.Error as e:
                # 如果添加列失败，记录错误并继续
                print(f"添加 last_seen 列失败: {e}")
                conn.close()
                return
        
        # 更新用户最后活跃时间
        now = datetime.now(timezone.utc).isoformat()
        conn.execute('UPDATE user SET last_seen = ? WHERE id = ?', (now, self.id))
        conn.commit()
        conn.close()
        self.last_seen = now
    
    def get_last_seen_str(self):
        if not self.last_seen:
            return "从未活跃"
        
        try:
            if isinstance(self.last_seen, str):
                last_seen = datetime.fromisoformat(self.last_seen.replace('Z', '+00:00'))
            else:
                last_seen = self.last_seen
            
            now = datetime.now(timezone.utc)
            delta = now - last_seen
            
            if delta.days > 365:
                years = delta.days // 365
                return f"{years}年前"
            elif delta.days > 30:
                months = delta.days // 30
                return f"{months}个月前"
            elif delta.days > 0:
                return f"{delta.days}天前"
            elif delta.seconds > 3600:
                hours = delta.seconds // 3600
                return f"{hours}小时前"
            elif delta.seconds > 60:
                minutes = delta.seconds // 60
                return f"{minutes}分钟前"
            else:
                return "刚刚"
        except Exception as e:
            return "未知"
    
    @staticmethod
    def get_by_id(user_id):
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        
        if user_data is None:
            return None
        
        # 检查是否存在 last_seen 字段
        last_seen = None
        if 'last_seen' in user_data.keys():
            last_seen = user_data['last_seen']
            
        # 检查是否存在 banned_reason 字段
        banned_reason = None
        if 'banned_reason' in user_data.keys():
            banned_reason = user_data['banned_reason']
            
        return User(
            id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password'],
            created_at=user_data['created_at'],
            is_admin=bool(user_data['is_admin']),
            is_sub_admin=bool(user_data['is_sub_admin']),
            is_banned=bool(user_data['is_banned']),
            banned_reason=banned_reason,
            last_seen=last_seen
        )
    
    @staticmethod
    def get_by_username(username):
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user_data is None:
            return None
            
        # 检查是否存在 last_seen 字段
        last_seen = None
        if 'last_seen' in user_data.keys():
            last_seen = user_data['last_seen']
            
        # 检查是否存在 banned_reason 字段
        banned_reason = None
        if 'banned_reason' in user_data.keys():
            banned_reason = user_data['banned_reason']
        
        return User(
            id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password'],
            created_at=user_data['created_at'],
            is_admin=bool(user_data['is_admin']),
            is_sub_admin=bool(user_data['is_sub_admin']),
            is_banned=bool(user_data['is_banned']),
            banned_reason=banned_reason,
            last_seen=last_seen
        )
    
    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM user WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user_data is None:
            return None
            
        # 检查是否存在 last_seen 字段
        last_seen = None
        if 'last_seen' in user_data.keys():
            last_seen = user_data['last_seen']
            
        # 检查是否存在 banned_reason 字段
        banned_reason = None
        if 'banned_reason' in user_data.keys():
            banned_reason = user_data['banned_reason']
        
        return User(
            id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password'],
            created_at=user_data['created_at'],
            is_admin=bool(user_data['is_admin']),
            is_sub_admin=bool(user_data['is_sub_admin']),
            is_banned=bool(user_data['is_banned']),
            banned_reason=banned_reason,
            last_seen=last_seen
        )
    
    @staticmethod
    def get_all(page=1, per_page=10):
        conn = get_db_connection()
        offset = (page - 1) * per_page
        
        # 获取总记录数
        total = conn.execute('SELECT COUNT(*) FROM user').fetchone()[0]
        
        # 获取分页数据
        users_data = conn.execute(
            'SELECT * FROM user ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (per_page, offset)
        ).fetchall()
        
        users = []
        for user_data in users_data:
            # 检查是否存在 last_seen 字段
            last_seen = None
            if 'last_seen' in user_data.keys():
                last_seen = user_data['last_seen']
                
            # 检查是否存在 banned_reason 字段
            banned_reason = None
            if 'banned_reason' in user_data.keys():
                banned_reason = user_data['banned_reason']
                
            users.append(User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password'],
                created_at=user_data['created_at'],
                is_admin=bool(user_data['is_admin']),
                is_sub_admin=bool(user_data['is_sub_admin']),
                is_banned=bool(user_data['is_banned']),
                banned_reason=banned_reason,
                last_seen=last_seen
            ))
        
        # 创建分页对象
        pagination = Pagination(page, per_page, total, users)
        conn.close()
        
        return pagination

class Post:
    def __init__(self, id=None, title=None, content=None, created_at=None, user_id=None,
                 is_deleted=False, deleted_at=None, deleted_by=None, is_pinned=False,
                 is_tourist_post=False, is_approved=None):
        self.id = id
        self.title = title
        self.content = content
        self.created_at = created_at
        self.user_id = user_id
        self.is_deleted = is_deleted
        self.deleted_at = deleted_at
        self.deleted_by = deleted_by
        self.is_pinned = is_pinned
        self.is_tourist_post = is_tourist_post
        self.is_approved = is_approved
        self._user = None
        self._deleter = None
    
    def save(self):
        conn = get_db_connection()
        
        if self.id is None:
            # 创建新反馈
            conn.execute(
                'INSERT INTO post (title, content, user_id, is_pinned, is_tourist_post, is_approved) VALUES (?, ?, ?, ?, ?, ?)',
                (self.title, self.content, self.user_id, int(self.is_pinned), int(self.is_tourist_post), self.is_approved)
            )
            self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        else:
            # 更新现有反馈
            conn.execute(
                'UPDATE post SET title = ?, content = ?, is_deleted = ?, deleted_at = ?, deleted_by = ?, is_pinned = ?, is_tourist_post = ?, is_approved = ? WHERE id = ?',
                (self.title, self.content, int(self.is_deleted), self.deleted_at, self.deleted_by, int(self.is_pinned), int(self.is_tourist_post), self.is_approved, self.id)
            )
        
        conn.commit()
        conn.close()
        return self
    
    def soft_delete(self, deleted_by_user_id):
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc).isoformat()
        self.deleted_by = deleted_by_user_id
        self.save()
        return self
    
    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save()
        return self
    
    @property
    def user(self):
        if self._user is None and self.user_id is not None:
            self._user = User.get_by_id(self.user_id)
        return self._user
    
    @property
    def deleter(self):
        if self._deleter is None and self.deleted_by is not None:
            self._deleter = User.get_by_id(self.deleted_by)
        return self._deleter
    
    @property
    def has_accepted_comment(self):
        """检查该帖子是否有被采纳的评论"""
        conn = get_db_connection()
        result = conn.execute(
            'SELECT COUNT(*) FROM comment WHERE post_id = ? AND is_accepted = 1',
            (self.id,)
        ).fetchone()[0]
        conn.close()
        return result > 0
    
    @staticmethod
    def get_by_id(post_id):
        conn = get_db_connection()
        post_data = conn.execute('SELECT * FROM post WHERE id = ?', (post_id,)).fetchone()
        conn.close()
        
        if post_data is None:
            return None
        
        return Post(
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
            is_approved=post_data['is_approved'] if 'is_approved' in post_data.keys() else None
        )
    
    @staticmethod
    def get_all(page=1, per_page=10, include_deleted=False):
        conn = get_db_connection()
        offset = (page - 1) * per_page
        
        # 获取总记录数
        if include_deleted:
            total = conn.execute('SELECT COUNT(*) FROM post').fetchone()[0]
        else:
            total = conn.execute('SELECT COUNT(*) FROM post WHERE (is_deleted = 0 OR is_deleted IS NULL) AND (is_tourist_post = 0 OR is_approved = 1)').fetchone()[0]
        
        # 获取分页数据
        if include_deleted:
            posts_data = conn.execute(
                'SELECT * FROM post ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?',
                (per_page, offset)
            ).fetchall()
        else:
            posts_data = conn.execute(
                'SELECT * FROM post WHERE (is_deleted = 0 OR is_deleted IS NULL) AND (is_tourist_post = 0 OR is_approved = 1) ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?',
                (per_page, offset)
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
                is_approved=post_data['is_approved'] if 'is_approved' in post_data.keys() else None
            ))
        
        # 创建分页对象
        pagination = Pagination(page, per_page, total, posts)
        conn.close()
        
        return pagination
    
    def pin(self):
        """将反馈置顶"""
        self.is_pinned = True
        self.save()
        return self
    
    def unpin(self):
        """取消反馈置顶"""
        self.is_pinned = False
        self.save()
        return self
    
    def approve(self):
        """审核通过帖子"""
        self.is_approved = True
        self.save()
        return self
    
    def reject(self):
        """拒绝帖子审核"""
        self.is_approved = False
        # 确保不将帖子标记为已删除
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save()
        return self

class Comment:
    def __init__(self, id=None, content=None, created_at=None, user_id=None, post_id=None,
                 is_deleted=False, deleted_at=None, deleted_by=None, parent_id=None, is_accepted=False, accepted_by=None):
        self.id = id
        self.content = content
        self.created_at = created_at
        self.user_id = user_id
        self.post_id = post_id
        self.is_deleted = is_deleted
        self.deleted_at = deleted_at
        self.deleted_by = deleted_by
        self.parent_id = parent_id  # 回复的父评论ID
        self.is_accepted = is_accepted  # 是否被采纳
        self.accepted_by = accepted_by  # 谁采纳了评论
        self._user = None
        self._deleter = None
        self._post = None
        self._parent = None
        self._replies = None
        self._accepted_by_user = None
    
    def save(self):
        conn = get_db_connection()
        
        if self.id is None:
            # 创建新评论
            conn.execute(
                'INSERT INTO comment (content, user_id, post_id, parent_id, is_accepted, accepted_by) VALUES (?, ?, ?, ?, ?, ?)',
                (self.content, self.user_id, self.post_id, self.parent_id, int(self.is_accepted), self.accepted_by)
            )
            self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        else:
            # 检查表结构是否包含所需字段
            cursor = conn.cursor()
            table_info = cursor.execute("PRAGMA table_info(comment)").fetchall()
            columns = [column[1] for column in table_info]
            
            # 构建更新语句，只包含存在的列
            update_fields = []
            values = []
            
            # 基本字段
            update_fields.append("content = ?")
            values.append(self.content)
            
            if "is_deleted" in columns:
                update_fields.append("is_deleted = ?")
                values.append(int(self.is_deleted))
            
            if "deleted_at" in columns:
                update_fields.append("deleted_at = ?")
                values.append(self.deleted_at)
            
            if "deleted_by" in columns:
                update_fields.append("deleted_by = ?")
                values.append(self.deleted_by)
            
            if "parent_id" in columns:
                update_fields.append("parent_id = ?")
                values.append(self.parent_id)
            
            if "is_accepted" in columns:
                update_fields.append("is_accepted = ?")
                values.append(int(self.is_accepted))
            
            if "accepted_by" in columns:
                update_fields.append("accepted_by = ?")
                values.append(self.accepted_by)
            
            # 添加ID条件
            values.append(self.id)
            
            # 执行更新语句
            update_sql = f"UPDATE comment SET {', '.join(update_fields)} WHERE id = ?"
            conn.execute(update_sql, values)
        
        conn.commit()
        conn.close()
        return self
    
    def soft_delete(self, deleted_by_user_id):
        """软删除评论"""
        # 设置已删除状态
        self.is_deleted = True
        self.deleted_by = deleted_by_user_id
        
        # 设置删除时间
        from datetime import datetime, timezone
        self.deleted_at = datetime.now(timezone.utc).isoformat()
        
        # 打印调试信息，确认只删除当前评论
        print(f"正在删除评论 ID={self.id}, parent_id={self.parent_id}")
        
        # 使用save方法保存更改，确保更新限定在当前评论ID上
        self.save()
        return self
    
    def restore(self):
        """恢复已删除的评论"""
        conn = get_db_connection()
        
        # 检查表结构是否包含所需字段
        cursor = conn.cursor()
        table_info = cursor.execute("PRAGMA table_info(comment)").fetchall()
        columns = [column[1] for column in table_info]
        
        # 基础恢复 - is_deleted总是应该存在
        update_fields = ["is_deleted = 0"]
        
        # 其他字段根据表结构决定是否更新
        if "deleted_at" in columns:
            update_fields.append("deleted_at = NULL")
        
        if "deleted_by" in columns:
            update_fields.append("deleted_by = NULL")
        
        # 执行更新语句
        update_sql = f"UPDATE comment SET {', '.join(update_fields)} WHERE id = ?"
        conn.execute(update_sql, (self.id,))
        
        conn.commit()
        conn.close()
        
        # 更新本地对象
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
    
    def accept(self, accepted_by_user_id):
        """采纳评论"""
        # 先将同一帖子的所有评论的采纳状态重置
        conn = get_db_connection()
        conn.execute('''
        UPDATE comment SET is_accepted = 0, accepted_by = NULL
        WHERE post_id = ? AND id != ?
        ''', (self.post_id, self.id))
        
        # 将当前评论设为采纳
        conn.execute('''
        UPDATE comment SET is_accepted = 1, accepted_by = ?
        WHERE id = ?
        ''', (accepted_by_user_id, self.id))
        conn.commit()
        conn.close()
            
        self.is_accepted = 1
        self.accepted_by = accepted_by_user_id
        return True
    
    def cancel_accept(self):
        """取消采纳"""
        conn = get_db_connection()
        conn.execute('''
        UPDATE comment SET is_accepted = 0, accepted_by = NULL
        WHERE id = ?
        ''', (self.id,))
        conn.commit()
        conn.close()
            
        self.is_accepted = 0
        self.accepted_by = None
        return True

    @property
    def user(self):
        """获取评论用户"""
        return User.get_by_id(self.user_id)
    
    @property
    def post(self):
        """获取评论所属帖子"""
        return Post.get_by_id(self.post_id)
    
    @property
    def parent(self):
        """获取父评论"""
        if self.parent_id:
            return Comment.get_by_id(self.parent_id)
        return None
    
    @property
    def accepted_by_user(self):
        """获取采纳人"""
        if self.accepted_by:
            return User.get_by_id(self.accepted_by)
        return None
    
    @property
    def deleter(self):
        if self._deleter is None and self.deleted_by is not None:
            self._deleter = User.get_by_id(self.deleted_by)
        return self._deleter
    
    @property
    def deleted_by_user(self):
        """获取删除评论的用户"""
        if self.deleted_by:
            return User.get_by_id(self.deleted_by)
        return None
    
    @property
    def replies(self):
        """获取回复列表"""
        if self._replies is None:
            # 根据实际情况需要传递include_deleted参数
            # 注意：这里我们保留默认值True，管理员可以看到所有评论
            # 在前端模板中可以根据用户权限决定是否显示
            self._replies = Comment.get_replies_by_comment_id(self.id)
            # 确保每个回复都加载它们的用户信息，防止页面渲染时出现问题
            for reply in self._replies:
                _ = reply.user  # 触发用户信息的懒加载
                _ = reply.parent  # 确保父评论已加载
                if reply.parent_id and reply.parent:
                    _ = reply.parent.user  # 确保父评论的用户已加载
        return self._replies
    
    @staticmethod
    def get_by_id(comment_id):
        conn = get_db_connection()
        comment_data = conn.execute('SELECT * FROM comment WHERE id = ?', (comment_id,)).fetchone()
        conn.close()
        
        if comment_data is None:
            return None
        
        # 获取所有列名
        columns = comment_data.keys()
        
        return Comment(
            id=comment_data['id'],
            content=comment_data['content'],
            created_at=comment_data['created_at'],
            user_id=comment_data['user_id'],
            post_id=comment_data['post_id'],
            is_deleted=bool(comment_data['is_deleted']) if 'is_deleted' in columns else False,
            deleted_at=comment_data['deleted_at'] if 'deleted_at' in columns else None,
            deleted_by=comment_data['deleted_by'] if 'deleted_by' in columns else None,
            parent_id=comment_data['parent_id'] if 'parent_id' in columns else None,
            is_accepted=bool(comment_data['is_accepted']) if 'is_accepted' in columns else False,
            accepted_by=comment_data['accepted_by'] if 'accepted_by' in columns else None
        )
    
    @staticmethod
    def get_comments_by_post_id(post_id, include_deleted=False):
        conn = get_db_connection()
        
        if include_deleted:
            comments_data = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? AND (parent_id IS NULL OR parent_id = 0) ORDER BY is_accepted DESC, created_at',
                (post_id,)
            ).fetchall()
        else:
            comments_data = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? AND (is_deleted = 0 OR is_deleted IS NULL) AND (parent_id IS NULL OR parent_id = 0) ORDER BY is_accepted DESC, created_at',
                (post_id,)
            ).fetchall()
        
        comments = []
        for comment_data in comments_data:
            # 获取所有列名
            columns = comment_data.keys()
            
            comment = Comment(
                id=comment_data['id'],
                content=comment_data['content'],
                created_at=comment_data['created_at'],
                user_id=comment_data['user_id'],
                post_id=comment_data['post_id'],
                is_deleted=bool(comment_data['is_deleted']) if 'is_deleted' in columns else False,
                deleted_at=comment_data['deleted_at'] if 'deleted_at' in columns else None,
                deleted_by=comment_data['deleted_by'] if 'deleted_by' in columns else None,
                parent_id=comment_data['parent_id'] if 'parent_id' in columns else None,
                is_accepted=bool(comment_data['is_accepted']) if 'is_accepted' in columns else False,
                accepted_by=comment_data['accepted_by'] if 'accepted_by' in columns else None
            )
            comments.append(comment)
        
        conn.close()
        return comments
    
    @staticmethod
    def get_replies_by_comment_id(comment_id, include_deleted=True, depth=0, max_depth=5):
        """
        获取评论的回复列表，支持多级嵌套
        
        Args:
            comment_id: 评论ID
            include_deleted: 是否包含已删除的评论，默认为True表示即使被删除也显示
            depth: 当前递归深度
            max_depth: 最大递归深度，防止无限递归
        """
        if depth > max_depth:
            return []  # 防止过深递归
            
        conn = get_db_connection()
        
        # 根据include_deleted参数决定是否包含已删除评论
        if include_deleted:
            replies_data = conn.execute(
                'SELECT * FROM comment WHERE parent_id = ? ORDER BY is_accepted DESC, created_at',
                (comment_id,)
            ).fetchall()
        else:
            replies_data = conn.execute(
                'SELECT * FROM comment WHERE parent_id = ? AND (is_deleted = 0 OR is_deleted IS NULL) ORDER BY is_accepted DESC, created_at',
                (comment_id,)
            ).fetchall()
        
        replies = []
        for reply_data in replies_data:
            # 获取所有列名
            columns = reply_data.keys()
            
            reply = Comment(
                id=reply_data['id'],
                content=reply_data['content'],
                created_at=reply_data['created_at'],
                user_id=reply_data['user_id'],
                post_id=reply_data['post_id'],
                is_deleted=bool(reply_data['is_deleted']) if 'is_deleted' in columns else False,
                deleted_at=reply_data['deleted_at'] if 'deleted_at' in columns else None,
                deleted_by=reply_data['deleted_by'] if 'deleted_by' in columns else None,
                parent_id=reply_data['parent_id'] if 'parent_id' in columns else None,
                is_accepted=bool(reply_data['is_accepted']) if 'is_accepted' in columns else False,
                accepted_by=reply_data['accepted_by'] if 'accepted_by' in columns else None
            )
            
            # 预加载相关信息，避免在模板渲染时出现问题
            _ = reply.user  # 触发用户信息的懒加载
            _ = reply.parent  # 确保父评论已加载
            if reply.parent_id and reply.parent:
                _ = reply.parent.user  # 确保父评论的用户已加载
            
            # 递归获取这个回复的回复
            reply._replies = Comment.get_replies_by_comment_id(
                reply.id, 
                include_deleted=include_deleted,
                depth=depth+1,
                max_depth=max_depth
            )
            
            replies.append(reply)
        
        conn.close()
        return replies

    @staticmethod
    def get_all_accepted_comments_by_post_id(post_id, include_deleted=False):
        """
        获取帖子所有已采纳的评论(包括子评论)
        
        Args:
            post_id: 帖子ID
            include_deleted: 是否包含已删除的评论
        """
        conn = get_db_connection()
        
        # 获取当前帖子下所有已采纳的评论（不限制parent_id）
        if include_deleted:
            query = 'SELECT * FROM comment WHERE post_id = ? AND is_accepted = 1 ORDER BY created_at'
        else:
            query = 'SELECT * FROM comment WHERE post_id = ? AND is_accepted = 1 AND (is_deleted = 0 OR is_deleted IS NULL) ORDER BY created_at'
        
        accepted_comments_data = conn.execute(query, (post_id,)).fetchall()
        
        # 打印调试信息
        print(f"SQL查询采纳评论数量: {len(accepted_comments_data)}")
        
        accepted_comments = []
        for comment_data in accepted_comments_data:
            # 获取所有列名
            columns = comment_data.keys()
            
            comment = Comment(
                id=comment_data['id'],
                content=comment_data['content'],
                created_at=comment_data['created_at'],
                user_id=comment_data['user_id'],
                post_id=comment_data['post_id'],
                is_deleted=bool(comment_data['is_deleted']) if 'is_deleted' in columns else False,
                deleted_at=comment_data['deleted_at'] if 'deleted_at' in columns else None,
                deleted_by=comment_data['deleted_by'] if 'deleted_by' in columns else None,
                parent_id=comment_data['parent_id'] if 'parent_id' in columns else None,
                is_accepted=bool(comment_data['is_accepted']) if 'is_accepted' in columns else False,
                accepted_by=comment_data['accepted_by'] if 'accepted_by' in columns else None
            )
            
            # 确保加载用户和父评论信息
            _ = comment.user  # 触发lazy loading
            _ = comment.accepted_by_user  # 触发lazy loading
            if comment.parent_id:
                _ = comment.parent  # 触发lazy loading
            
            accepted_comments.append(comment)
        
        conn.close()
        return accepted_comments

class Pagination:
    def __init__(self, page, per_page, total, items):
        self.page = page
        self.per_page = per_page
        self.total = total
        self.items = items
    
    @property
    def pages(self):
        return math.ceil(self.total / self.per_page) if self.total > 0 else 1
    
    @property
    def has_prev(self):
        return self.page > 1
    
    @property
    def has_next(self):
        return self.page < self.pages
    
    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None
    
    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num 

# 活动日志类
class ActivityLog:
    def __init__(self, id=None, user_id=None, action=None, target_type=None, target_id=None, description=None, created_at=None):
        self.id = id
        self.user_id = user_id
        self.action = action  # 例如: post_create, post_delete, comment_delete, user_ban等
        self.target_type = target_type  # 例如: post, comment, user
        self.target_id = target_id  # 目标ID
        self.description = description  # 详细描述
        self.created_at = created_at or self.get_current_time()
        
    def get_current_time(self):
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
    def save(self):
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO activity_log (user_id, action, target_type, target_id, description, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (self.user_id, self.action, self.target_type, self.target_id, self.description, self.created_at)
        )
        conn.commit()
        
        # 获取新插入记录的ID
        self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        conn.close()
        return self
    
    @staticmethod
    def create_log(user_id, action, target_type, target_id, description):
        log = ActivityLog(user_id=user_id, action=action, target_type=target_type, target_id=target_id, description=description)
        return log.save()
    
    @staticmethod
    def get_recent_logs(limit=20):
        conn = get_db_connection()
        logs = conn.execute(
            '''
            SELECT a.*, u.username as username 
            FROM activity_log a 
            JOIN user u ON a.user_id = u.id 
            ORDER BY a.created_at DESC 
            LIMIT ?
            ''', 
            (limit,)
        ).fetchall()
        conn.close()
        
        result = []
        for log in logs:
            result.append({
                'id': log['id'],
                'user_id': log['user_id'],
                'username': log['username'],
                'action': log['action'],
                'target_type': log['target_type'],
                'target_id': log['target_id'],
                'description': log['description'],
                'time': log['created_at']
            })
        return result 

class Settings:
    @staticmethod
    def get(key, default=None):
        """获取设置值"""
        conn = get_db_connection()
        setting = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        conn.close()
        
        if setting:
            return setting['value']
        return default
    
    @staticmethod
    def set(key, value, description=None):
        """更新设置值"""
        conn = get_db_connection()
        now = datetime.now().isoformat()
        
        # 检查设置是否已存在
        existing = conn.execute('SELECT 1 FROM settings WHERE key = ?', (key,)).fetchone()
        
        if existing:
            if description:
                conn.execute('UPDATE settings SET value = ?, description = ?, updated_at = ? WHERE key = ?',
                           (value, description, now, key))
            else:
                conn.execute('UPDATE settings SET value = ?, updated_at = ? WHERE key = ?',
                           (value, now, key))
        else:
            conn.execute('INSERT INTO settings (key, value, description, updated_at) VALUES (?, ?, ?, ?)',
                       (key, value, description, now))
        
        conn.commit()
        conn.close()
        return True
    
    @staticmethod
    def get_all():
        """获取所有设置"""
        conn = get_db_connection()
        settings = conn.execute('SELECT key, value, description, updated_at FROM settings').fetchall()
        conn.close()
        return settings 