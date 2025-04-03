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
    # 确保数据目录存在
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        is_admin BOOLEAN NOT NULL DEFAULT 0,
        is_sub_admin BOOLEAN NOT NULL DEFAULT 0,
        is_banned BOOLEAN NOT NULL DEFAULT 0,
        banned_reason TEXT,
        last_seen TIMESTAMP
    )
    ''')
    
    # 创建帖子表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS post (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER NOT NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT 0,
        deleted_at TIMESTAMP,
        deleted_by INTEGER,
        is_pinned BOOLEAN NOT NULL DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES user (id),
        FOREIGN KEY (deleted_by) REFERENCES user (id)
    )
    ''')
    
    # 创建评论表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS comment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        is_deleted BOOLEAN NOT NULL DEFAULT 0,
        deleted_at TIMESTAMP,
        deleted_by INTEGER,
        FOREIGN KEY (user_id) REFERENCES user (id),
        FOREIGN KEY (post_id) REFERENCES post (id),
        FOREIGN KEY (deleted_by) REFERENCES user (id)
    )
    ''')
    
    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_user_id ON post (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_created_at ON post (created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_post_is_deleted ON post (is_deleted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_post_id ON comment (post_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_user_id ON comment (user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_comment_is_deleted ON comment (is_deleted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_is_banned ON user (is_banned)')
    
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
                'INSERT INTO user (username, email, password_hash, is_admin, is_sub_admin, is_banned, banned_reason) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (self.username, self.email, self.password_hash, int(self.is_admin), int(self.is_sub_admin), int(self.is_banned), self.banned_reason)
            )
            self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        else:
            # 更新现有用户
            conn.execute(
                'UPDATE user SET username = ?, email = ?, password_hash = ?, is_admin = ?, is_sub_admin = ?, is_banned = ?, banned_reason = ? WHERE id = ?',
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
        now = datetime.now(timezone.utc)
        conn = get_db_connection()
        conn.execute(
            'UPDATE user SET last_seen = ? WHERE id = ?',
            (now.isoformat(), self.id)
        )
        conn.commit()
        conn.close()
        self.last_seen = now
        return self
    
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
        
        return User(
            id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password_hash'],
            created_at=user_data['created_at'],
            is_admin=bool(user_data['is_admin']),
            is_sub_admin=bool(user_data['is_sub_admin']),
            is_banned=bool(user_data['is_banned']),
            banned_reason=user_data['banned_reason'],
            last_seen=user_data['last_seen']
        )
    
    @staticmethod
    def get_by_username(username):
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user_data is None:
            return None
        
        return User(
            id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password_hash'],
            created_at=user_data['created_at'],
            is_admin=bool(user_data['is_admin']),
            is_sub_admin=bool(user_data['is_sub_admin']),
            is_banned=bool(user_data['is_banned']),
            banned_reason=user_data['banned_reason'],
            last_seen=user_data['last_seen']
        )
    
    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM user WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user_data is None:
            return None
        
        return User(
            id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password_hash'],
            created_at=user_data['created_at'],
            is_admin=bool(user_data['is_admin']),
            is_sub_admin=bool(user_data['is_sub_admin']),
            is_banned=bool(user_data['is_banned']),
            banned_reason=user_data['banned_reason'],
            last_seen=user_data['last_seen']
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
            users.append(User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data['email'],
                password_hash=user_data['password_hash'],
                created_at=user_data['created_at'],
                is_admin=bool(user_data['is_admin']),
                is_sub_admin=bool(user_data['is_sub_admin']),
                is_banned=bool(user_data['is_banned']),
                banned_reason=user_data['banned_reason'],
                last_seen=user_data['last_seen']
            ))
        
        # 创建分页对象
        pagination = Pagination(page, per_page, total, users)
        conn.close()
        
        return pagination

class Post:
    def __init__(self, id=None, title=None, content=None, created_at=None, user_id=None,
                 is_deleted=False, deleted_at=None, deleted_by=None, is_pinned=False):
        self.id = id
        self.title = title
        self.content = content
        self.created_at = created_at
        self.user_id = user_id
        self.is_deleted = is_deleted
        self.deleted_at = deleted_at
        self.deleted_by = deleted_by
        self.is_pinned = is_pinned
        self._user = None
        self._deleter = None
    
    def save(self):
        conn = get_db_connection()
        
        if self.id is None:
            # 创建新反馈
            conn.execute(
                'INSERT INTO post (title, content, user_id, is_pinned) VALUES (?, ?, ?, ?)',
                (self.title, self.content, self.user_id, int(self.is_pinned))
            )
            self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        else:
            # 更新现有反馈
            conn.execute(
                'UPDATE post SET title = ?, content = ?, is_deleted = ?, deleted_at = ?, deleted_by = ?, is_pinned = ? WHERE id = ?',
                (self.title, self.content, int(self.is_deleted), self.deleted_at, self.deleted_by, int(self.is_pinned), self.id)
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
            is_pinned=bool(post_data['is_pinned']) if 'is_pinned' in post_data.keys() else False
        )
    
    @staticmethod
    def get_all(page=1, per_page=10, include_deleted=False):
        conn = get_db_connection()
        offset = (page - 1) * per_page
        
        # 获取总记录数
        if include_deleted:
            total = conn.execute('SELECT COUNT(*) FROM post').fetchone()[0]
        else:
            total = conn.execute('SELECT COUNT(*) FROM post WHERE is_deleted = 0 OR is_deleted IS NULL').fetchone()[0]
        
        # 获取分页数据
        if include_deleted:
            posts_data = conn.execute(
                'SELECT * FROM post ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?',
                (per_page, offset)
            ).fetchall()
        else:
            posts_data = conn.execute(
                'SELECT * FROM post WHERE is_deleted = 0 OR is_deleted IS NULL ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?',
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
                is_pinned=bool(post_data['is_pinned']) if 'is_pinned' in post_data.keys() else False
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

class Comment:
    def __init__(self, id=None, content=None, created_at=None, user_id=None, post_id=None,
                 is_deleted=False, deleted_at=None, deleted_by=None):
        self.id = id
        self.content = content
        self.created_at = created_at
        self.user_id = user_id
        self.post_id = post_id
        self.is_deleted = is_deleted
        self.deleted_at = deleted_at
        self.deleted_by = deleted_by
        self._user = None
        self._deleter = None
        self._post = None
    
    def save(self):
        conn = get_db_connection()
        
        if self.id is None:
            # 创建新评论
            conn.execute(
                'INSERT INTO comment (content, user_id, post_id) VALUES (?, ?, ?)',
                (self.content, self.user_id, self.post_id)
            )
            self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        else:
            # 更新现有评论
            conn.execute(
                'UPDATE comment SET content = ?, is_deleted = ?, deleted_at = ?, deleted_by = ? WHERE id = ?',
                (self.content, int(self.is_deleted), self.deleted_at, self.deleted_by, self.id)
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
    def post(self):
        if self._post is None and self.post_id is not None:
            self._post = Post.get_by_id(self.post_id)
        return self._post
    
    @property
    def deleter(self):
        if self._deleter is None and self.deleted_by is not None:
            self._deleter = User.get_by_id(self.deleted_by)
        return self._deleter
    
    @staticmethod
    def get_by_id(comment_id):
        conn = get_db_connection()
        comment_data = conn.execute('SELECT * FROM comment WHERE id = ?', (comment_id,)).fetchone()
        conn.close()
        
        if comment_data is None:
            return None
        
        return Comment(
            id=comment_data['id'],
            content=comment_data['content'],
            created_at=comment_data['created_at'],
            user_id=comment_data['user_id'],
            post_id=comment_data['post_id'],
            is_deleted=bool(comment_data['is_deleted']) if 'is_deleted' in comment_data.keys() else False,
            deleted_at=comment_data['deleted_at'] if 'deleted_at' in comment_data.keys() else None,
            deleted_by=comment_data['deleted_by'] if 'deleted_by' in comment_data.keys() else None
        )
    
    @staticmethod
    def get_comments_by_post_id(post_id, include_deleted=False):
        conn = get_db_connection()
        
        if include_deleted:
            comments_data = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? ORDER BY created_at',
                (post_id,)
            ).fetchall()
        else:
            comments_data = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? AND (is_deleted = 0 OR is_deleted IS NULL) ORDER BY created_at',
                (post_id,)
            ).fetchall()
        
        comments = []
        for comment_data in comments_data:
            comments.append(Comment(
                id=comment_data['id'],
                content=comment_data['content'],
                created_at=comment_data['created_at'],
                user_id=comment_data['user_id'],
                post_id=comment_data['post_id'],
                is_deleted=bool(comment_data['is_deleted']) if 'is_deleted' in comment_data.keys() else False,
                deleted_at=comment_data['deleted_at'] if 'deleted_at' in comment_data.keys() else None,
                deleted_by=comment_data['deleted_by'] if 'deleted_by' in comment_data.keys() else None
            ))
        
        conn.close()
        return comments

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