import sqlite3
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
import math
import os

# 数据库路径设置
db_dir = os.environ.get('DB_DIR', os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(db_dir, 'feedback.db')

def get_db_connection():
    os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    """初始化并以非破坏方式升级数据库结构。"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('PRAGMA journal_mode = WAL')
        cursor.execute('BEGIN IMMEDIATE')

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

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS comment (
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

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            description TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        migrations = {
            'user': {
                'is_sub_admin': 'BOOLEAN NOT NULL DEFAULT 0',
                'is_banned': 'BOOLEAN NOT NULL DEFAULT 0',
                'banned_reason': 'TEXT',
                'last_seen': 'TIMESTAMP',
                'posts': 'INTEGER NOT NULL DEFAULT 0',
                'comments': 'INTEGER NOT NULL DEFAULT 0',
            },
            'post': {
                'is_deleted': 'BOOLEAN NOT NULL DEFAULT 0',
                'deleted_by': 'INTEGER',
                'deleted_at': 'TIMESTAMP',
                'is_pinned': 'BOOLEAN NOT NULL DEFAULT 0',
                'is_tourist_post': 'BOOLEAN NOT NULL DEFAULT 0',
                'is_approved': 'BOOLEAN',
            },
            'comment': {
                'is_deleted': 'BOOLEAN NOT NULL DEFAULT 0',
                'deleted_at': 'TIMESTAMP',
                'deleted_by': 'INTEGER',
                'parent_id': 'INTEGER',
                'is_accepted': 'BOOLEAN NOT NULL DEFAULT 0',
                'accepted_by': 'INTEGER',
            },
        }
        for table, additions in migrations.items():
            columns = {
                column['name']
                for column in cursor.execute(f'PRAGMA table_info({table})').fetchall()
            }
            for name, definition in additions.items():
                if name not in columns:
                    cursor.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')

        cursor.execute('''UPDATE user SET
                              is_admin = COALESCE(is_admin, 0),
                              is_sub_admin = CASE WHEN is_admin = 1 THEN 0 ELSE COALESCE(is_sub_admin, 0) END,
                              is_banned = COALESCE(is_banned, 0),
                              posts = COALESCE(posts, 0),
                              comments = COALESCE(comments, 0)
                          WHERE is_admin IS NULL OR is_sub_admin IS NULL
                             OR is_banned IS NULL OR posts IS NULL OR comments IS NULL
                             OR (is_admin = 1 AND is_sub_admin = 1)''')
        cursor.execute('''UPDATE post SET
                              is_deleted = COALESCE(is_deleted, 0),
                              is_pinned = COALESCE(is_pinned, 0),
                              is_tourist_post = COALESCE(is_tourist_post, 0)
                          WHERE is_deleted IS NULL OR is_pinned IS NULL
                             OR is_tourist_post IS NULL''')
        cursor.execute('''UPDATE comment SET
                              is_deleted = COALESCE(is_deleted, 0),
                              is_accepted = COALESCE(is_accepted, 0)
                          WHERE is_deleted IS NULL OR is_accepted IS NULL''')

        indexes = (
            ('idx_post_user_id', 'post', 'user_id'),
            ('idx_post_visibility', 'post', 'is_deleted, is_tourist_post, is_approved'),
            ('idx_post_pinned_created', 'post', 'is_pinned, created_at'),
            ('idx_comment_user_id', 'comment', 'user_id'),
            ('idx_comment_post_parent', 'comment', 'post_id, parent_id'),
            ('idx_comment_post_status', 'comment', 'post_id, is_deleted, is_accepted'),
            ('idx_activity_created_at', 'activity_log', 'created_at'),
        )
        for name, table, columns in indexes:
            cursor.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})')

        if not cursor.execute('SELECT 1 FROM user WHERE username = ?', ('admin',)).fetchone():
            password = os.environ.get('ADMIN_PASSWORD', 'admin')
            cursor.execute(
                'INSERT INTO user (username, email, password, is_admin) VALUES (?, ?, ?, ?)',
                ('admin', 'admin@example.com', generate_password_hash(password), 1),
            )
        if not cursor.execute('SELECT 1 FROM user WHERE username = ?', ('tourist',)).fetchone():
            cursor.execute(
                'INSERT INTO user (username, email, password) VALUES (?, ?, ?)',
                ('tourist', 'tourist@example.com', generate_password_hash(os.urandom(32).hex())),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
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
            return None

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
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)
    
    def save(self):
        conn = get_db_connection()
        try:
            if self.id is None:
                conn.execute(
                    'INSERT INTO user (username, email, password, is_admin, is_sub_admin, is_banned, banned_reason) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (self.username, self.email, self.password_hash, int(self.is_admin), int(self.is_sub_admin), int(self.is_banned), self.banned_reason)
                )
                self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            else:
                conn.execute(
                    'UPDATE user SET username = ?, email = ?, password = ?, is_admin = ?, is_sub_admin = ?, is_banned = ?, banned_reason = ? WHERE id = ?',
                    (self.username, self.email, self.password_hash, int(self.is_admin), int(self.is_sub_admin), int(self.is_banned), self.banned_reason, self.id)
                )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
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
        """最多每分钟更新一次活跃时间，避免每个请求都写数据库。"""
        now = datetime.now(timezone.utc).isoformat()
        previous = parse_datetime(self.last_seen)
        if previous is not None:
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - previous).total_seconds() < 60:
                return

        conn = get_db_connection()
        try:
            conn.execute('UPDATE user SET last_seen = ? WHERE id = ?', (now, self.id))
            conn.commit()
        finally:
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
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            delta = now - last_seen
            if delta.total_seconds() < 0:
                return "刚刚"

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
        except (TypeError, ValueError, OverflowError):
            return "未知"

    @staticmethod
    def _from_row(user_data):
        if user_data is None:
            return None
        columns = user_data.keys()
        return User(
            id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password'],
            created_at=user_data['created_at'],
            is_admin=bool(user_data['is_admin']),
            is_sub_admin=bool(user_data['is_sub_admin']) if 'is_sub_admin' in columns else False,
            is_banned=bool(user_data['is_banned']) if 'is_banned' in columns else False,
            banned_reason=user_data['banned_reason'] if 'banned_reason' in columns else None,
            last_seen=user_data['last_seen'] if 'last_seen' in columns else None,
        )
    
    @staticmethod
    def get_by_id(user_id):
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM user WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        
        return User._from_row(user_data)
    
    @staticmethod
    def get_by_username(username):
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        return User._from_row(user_data)
    
    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        user_data = conn.execute(
            'SELECT * FROM user WHERE email = ? COLLATE NOCASE', (email,)
        ).fetchone()
        conn.close()
        
        return User._from_row(user_data)

    @staticmethod
    def get_by_ids(user_ids):
        ids = sorted({int(user_id) for user_id in user_ids if user_id is not None})
        if not ids:
            return {}
        placeholders = ','.join('?' for _ in ids)
        conn = get_db_connection()
        rows = conn.execute(
            f'SELECT * FROM user WHERE id IN ({placeholders})', ids
        ).fetchall()
        conn.close()
        return {row['id']: User._from_row(row) for row in rows}
    
    @staticmethod
    def get_all(page=1, per_page=10):
        page = max(1, int(page))
        per_page = max(1, int(per_page))
        conn = get_db_connection()
        total = conn.execute('SELECT COUNT(*) FROM user').fetchone()[0]
        page = min(page, max(1, math.ceil(total / per_page)))
        offset = (page - 1) * per_page

        # 获取分页数据
        users_data = conn.execute(
            'SELECT * FROM user ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (per_page, offset)
        ).fetchall()
        
        users = [User._from_row(user_data) for user_data in users_data]
        
        # 创建分页对象
        pagination = Pagination(page, per_page, total, users)
        conn.close()
        
        return pagination

class Post:
    def __init__(self, id=None, title=None, content=None, created_at=None, user_id=None,
                 is_deleted=False, deleted_at=None, deleted_by=None, is_pinned=False,
                 is_tourist_post=False, is_approved=None, comment_count=None,
                 has_accepted_comment=None):
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
        self._comment_count = comment_count
        self._has_accepted_comment = has_accepted_comment
    
    def save(self):
        conn = get_db_connection()
        try:
            if self.id is None:
                conn.execute(
                    'INSERT INTO post (title, content, user_id, is_pinned, is_tourist_post, is_approved) VALUES (?, ?, ?, ?, ?, ?)',
                    (self.title, self.content, self.user_id, int(self.is_pinned), int(self.is_tourist_post), self.is_approved)
                )
                self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            else:
                conn.execute(
                    'UPDATE post SET title = ?, content = ?, is_deleted = ?, deleted_at = ?, deleted_by = ?, is_pinned = ?, is_tourist_post = ?, is_approved = ? WHERE id = ?',
                    (self.title, self.content, int(self.is_deleted), self.deleted_at, self.deleted_by, int(self.is_pinned), int(self.is_tourist_post), self.is_approved, self.id)
                )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
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
        if self._has_accepted_comment is not None:
            return bool(self._has_accepted_comment)
        conn = get_db_connection()
        result = conn.execute(
            'SELECT COUNT(*) FROM comment WHERE post_id = ? AND is_accepted = 1 AND is_deleted = 0',
            (self.id,)
        ).fetchone()[0]
        conn.close()
        self._has_accepted_comment = result > 0
        return self._has_accepted_comment

    @property
    def total_comment_count(self):
        """获取该帖子的总评论数（包括所有层级的回复）"""
        if self._comment_count is not None:
            return self._comment_count
        conn = get_db_connection()
        result = conn.execute(
            'SELECT COUNT(*) FROM comment WHERE post_id = ? AND is_deleted = 0',
            (self.id,)
        ).fetchone()[0]
        conn.close()
        self._comment_count = result
        return self._comment_count

    @staticmethod
    def _from_row(post_data):
        if post_data is None:
            return None
        columns = post_data.keys()
        return Post(
            id=post_data['id'],
            title=post_data['title'],
            content=post_data['content'],
            created_at=post_data['created_at'],
            user_id=post_data['user_id'],
            is_deleted=bool(post_data['is_deleted']) if 'is_deleted' in columns else False,
            deleted_at=post_data['deleted_at'] if 'deleted_at' in columns else None,
            deleted_by=post_data['deleted_by'] if 'deleted_by' in columns else None,
            is_pinned=bool(post_data['is_pinned']) if 'is_pinned' in columns else False,
            is_tourist_post=bool(post_data['is_tourist_post']) if 'is_tourist_post' in columns else False,
            is_approved=(
                None if 'is_approved' not in columns or post_data['is_approved'] is None
                else bool(post_data['is_approved'])
            ),
            comment_count=post_data['comment_count'] if 'comment_count' in columns else None,
            has_accepted_comment=post_data['has_accepted_comment'] if 'has_accepted_comment' in columns else None,
        )

    @staticmethod
    def preload(posts):
        """批量预载作者和评论统计，避免模板渲染时逐条查询。"""
        posts = list(posts)
        users = User.get_by_ids(post.user_id for post in posts)
        for post in posts:
            post._user = users.get(post.user_id)

        missing_ids = [
            post.id for post in posts
            if post.id is not None and post._comment_count is None
        ]
        if not missing_ids:
            return posts
        placeholders = ','.join('?' for _ in missing_ids)
        conn = get_db_connection()
        rows = conn.execute(
            f'''SELECT post_id, COUNT(*) AS comment_count,
                       MAX(CASE WHEN is_accepted = 1 THEN 1 ELSE 0 END) AS has_accepted
                FROM comment
                WHERE is_deleted = 0 AND post_id IN ({placeholders})
                GROUP BY post_id''',
            missing_ids,
        ).fetchall()
        conn.close()
        stats = {row['post_id']: row for row in rows}
        for post in posts:
            if post.id not in missing_ids:
                continue
            row = stats.get(post.id)
            post._comment_count = row['comment_count'] if row else 0
            post._has_accepted_comment = bool(row['has_accepted']) if row else False
        return posts
    
    @staticmethod
    def get_by_id(post_id):
        conn = get_db_connection()
        post_data = conn.execute('SELECT * FROM post WHERE id = ?', (post_id,)).fetchone()
        conn.close()
        
        return Post._from_row(post_data)
    
    @staticmethod
    def get_all(page=1, per_page=10, include_deleted=False):
        page = max(1, int(page))
        per_page = max(1, int(per_page))
        conn = get_db_connection()
        if include_deleted:
            total = conn.execute('SELECT COUNT(*) FROM post').fetchone()[0]
        else:
            total = conn.execute('SELECT COUNT(*) FROM post WHERE is_deleted = 0 AND (is_tourist_post = 0 OR is_approved = 1)').fetchone()[0]
        page = min(page, max(1, math.ceil(total / per_page)))
        offset = (page - 1) * per_page

        # 获取分页数据
        if include_deleted:
            posts_data = conn.execute(
                '''SELECT p.*,
                          (SELECT COUNT(*) FROM comment c WHERE c.post_id = p.id AND c.is_deleted = 0) AS comment_count,
                          EXISTS(SELECT 1 FROM comment c WHERE c.post_id = p.id AND c.is_accepted = 1 AND c.is_deleted = 0) AS has_accepted_comment
                   FROM post p ORDER BY p.is_pinned DESC, p.created_at DESC LIMIT ? OFFSET ?''',
                (per_page, offset)
            ).fetchall()
        else:
            posts_data = conn.execute(
                '''SELECT p.*,
                          (SELECT COUNT(*) FROM comment c WHERE c.post_id = p.id AND c.is_deleted = 0) AS comment_count,
                          EXISTS(SELECT 1 FROM comment c WHERE c.post_id = p.id AND c.is_accepted = 1 AND c.is_deleted = 0) AS has_accepted_comment
                   FROM post p
                   WHERE p.is_deleted = 0 AND (p.is_tourist_post = 0 OR p.is_approved = 1)
                   ORDER BY p.is_pinned DESC, p.created_at DESC LIMIT ? OFFSET ?''',
                (per_page, offset)
            ).fetchall()

        posts = [Post._from_row(post_data) for post_data in posts_data]
        Post.preload(posts)
        
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
                 is_deleted=False, deleted_at=None, deleted_by=None, parent_id=None,
                 is_accepted=False, accepted_by=None, include_deleted=False, depth=0):
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
        self._include_deleted = include_deleted
        self.depth = depth
    
    def save(self):
        conn = get_db_connection()
        try:
            if self.id is None:
                conn.execute(
                    'INSERT INTO comment (content, user_id, post_id, parent_id, is_accepted, accepted_by) VALUES (?, ?, ?, ?, ?, ?)',
                    (self.content, self.user_id, self.post_id, self.parent_id, int(self.is_accepted), self.accepted_by)
                )
                self.id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            else:
                conn.execute(
                    '''UPDATE comment
                       SET content = ?, is_deleted = ?, deleted_at = ?, deleted_by = ?,
                           parent_id = ?, is_accepted = ?, accepted_by = ?
                       WHERE id = ?''',
                    (self.content, int(self.is_deleted), self.deleted_at,
                     self.deleted_by, self.parent_id, int(self.is_accepted),
                     self.accepted_by, self.id),
                )

            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
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
        if self._user is None and self.user_id is not None:
            self._user = User.get_by_id(self.user_id)
        return self._user
    
    @property
    def post(self):
        """获取评论所属帖子"""
        if self._post is None and self.post_id is not None:
            self._post = Post.get_by_id(self.post_id)
        return self._post
    
    @property
    def parent(self):
        """获取父评论"""
        if self._parent is None and self.parent_id:
            self._parent = Comment.get_by_id(self.parent_id)
        return self._parent
    
    @property
    def accepted_by_user(self):
        """获取采纳人"""
        if self._accepted_by_user is None and self.accepted_by:
            self._accepted_by_user = User.get_by_id(self.accepted_by)
        return self._accepted_by_user
    
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
            self._replies = Comment.get_replies_by_comment_id(
                self.id, include_deleted=self._include_deleted, parent=self
            )
        return self._replies

    @staticmethod
    def _from_row(comment_data, include_deleted=False, depth=0):
        if comment_data is None:
            return None
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
            accepted_by=comment_data['accepted_by'] if 'accepted_by' in columns else None,
            include_deleted=include_deleted,
            depth=depth,
        )

    @staticmethod
    def get_depth(comment_id, max_depth=100):
        """返回评论深度；检测到循环引用时按超深处理。"""
        conn = get_db_connection()
        current_id = comment_id
        depth = 0
        seen = set()
        try:
            while current_id:
                if current_id in seen or depth > max_depth:
                    return max_depth
                seen.add(current_id)
                row = conn.execute(
                    'SELECT parent_id FROM comment WHERE id = ?', (current_id,)
                ).fetchone()
                if row is None or not row['parent_id']:
                    return depth
                current_id = row['parent_id']
                depth += 1
            return depth
        finally:
            conn.close()
    
    @staticmethod
    def get_by_id(comment_id):
        conn = get_db_connection()
        comment_data = conn.execute('SELECT * FROM comment WHERE id = ?', (comment_id,)).fetchone()
        conn.close()
        
        return Comment._from_row(comment_data)
    
    @staticmethod
    def get_comments_by_post_id(post_id, include_deleted=False, max_depth=5):
        conn = get_db_connection()
        
        if include_deleted:
            comments_data = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? ORDER BY is_accepted DESC, created_at',
                (post_id,)
            ).fetchall()
        else:
            comments_data = conn.execute(
                'SELECT * FROM comment WHERE post_id = ? AND is_deleted = 0 ORDER BY is_accepted DESC, created_at',
                (post_id,)
            ).fetchall()
        conn.close()

        comments = [
            Comment._from_row(comment_data, include_deleted=include_deleted)
            for comment_data in comments_data
        ]
        users = User.get_by_ids(comment.user_id for comment in comments)
        for comment in comments:
            comment._user = users.get(comment.user_id)
            comment._replies = []

        comments_by_id = {comment.id: comment for comment in comments}
        roots = []
        for comment in comments:
            immediate_parent = comments_by_id.get(comment.parent_id)
            if immediate_parent is None:
                comment.depth = 0
                roots.append(comment)
                continue

            depth = 0
            ancestor_id = comment.parent_id
            seen = {comment.id}
            while ancestor_id in comments_by_id and depth <= max_depth:
                if ancestor_id in seen:
                    depth = max_depth + 1
                    break
                seen.add(ancestor_id)
                depth += 1
                ancestor_id = comments_by_id[ancestor_id].parent_id

            comment.depth = depth
            if depth <= max_depth:
                comment._parent = immediate_parent
                immediate_parent._replies.append(comment)

        return roots
    
    @staticmethod
    def get_replies_by_comment_id(comment_id, include_deleted=False, depth=0,
                                  max_depth=5, parent=None):
        """
        获取评论的回复列表，支持多级嵌套
        
        Args:
            comment_id: 评论ID
            include_deleted: 是否包含已删除的评论
            depth: 当前递归深度
            max_depth: 最大递归深度，防止无限递归
        """
        if depth >= max_depth:
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
        users = User.get_by_ids(reply_data['user_id'] for reply_data in replies_data)
        for reply_data in replies_data:
            reply = Comment._from_row(
                reply_data, include_deleted=include_deleted, depth=depth + 1
            )
            reply._user = users.get(reply.user_id)
            reply._parent = parent
            
            # 递归获取这个回复的回复
            reply._replies = Comment.get_replies_by_comment_id(
                reply.id, 
                include_deleted=include_deleted,
                depth=depth+1,
                max_depth=max_depth,
                parent=reply,
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
        
        accepted_comments = []
        user_ids = set()
        for comment_data in accepted_comments_data:
            user_ids.add(comment_data['user_id'])
            if comment_data['accepted_by']:
                user_ids.add(comment_data['accepted_by'])
        users = User.get_by_ids(user_ids)
        for comment_data in accepted_comments_data:
            comment = Comment._from_row(comment_data, include_deleted=include_deleted)
            comment._user = users.get(comment.user_id)
            comment._accepted_by_user = users.get(comment.accepted_by)
            
            accepted_comments.append(comment)
        
        conn.close()
        return accepted_comments

class Pagination:
    def __init__(self, page, per_page, total, items):
        self.page = max(1, int(page))
        self.per_page = max(1, int(per_page))
        self.total = max(0, int(total))
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
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
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
        return Settings.set_many({key: (value, description)})

    @staticmethod
    def set_many(values):
        """在单个事务中更新多项设置。"""
        conn = get_db_connection()
        now = datetime.now(timezone.utc).isoformat()
        try:
            for key, (value, description) in values.items():
                conn.execute(
                    '''INSERT INTO settings (key, value, description, updated_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(key) DO UPDATE SET
                           value = excluded.value,
                           description = COALESCE(excluded.description, settings.description),
                           updated_at = excluded.updated_at''',
                    (key, value, description, now),
                )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()
        return True
    
    @staticmethod
    def get_all():
        """获取所有设置"""
        conn = get_db_connection()
        settings = conn.execute('SELECT key, value, description, updated_at FROM settings').fetchall()
        conn.close()
        return settings 

    @staticmethod
    def get_dict():
        """一次读取全部设置，供单个请求复用。"""
        return {setting['key']: setting['value'] for setting in Settings.get_all()}
