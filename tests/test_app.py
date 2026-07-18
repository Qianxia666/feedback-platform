import os
import re
import shutil
import sqlite3
import tempfile
import unittest

import models
from app import create_app
from models import Comment, Post, Settings, User, init_db


class FeedbackPlatformTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        models.db_dir = self.temp_dir
        models.DB_PATH = os.path.join(self.temp_dir, 'feedback.db')
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def register(self, username, email, password='secret1'):
        return self.client.post('/register', data={
            'username': username,
            'email': email,
            'password': password,
            'password2': password,
        })

    def login(self, username, password):
        return self.client.post('/login', data={
            'username': username,
            'password': password,
        })

    def logout(self):
        return self.client.post('/logout')

    def test_database_initialization_is_idempotent(self):
        user = User(username='person', email='person@example.com')
        user.set_password('secret1')
        user.save()
        post = Post(title='Test issue', content='Long enough content', user_id=user.id)
        post.save()
        Comment(content='Useful reply', user_id=user.id, post_id=post.id).save()

        init_db()
        init_db()

        conn = sqlite3.connect(models.DB_PATH)
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM comment').fetchone()[0], 1)
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        finally:
            conn.close()

    def test_legacy_database_is_upgraded_without_data_loss(self):
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(models.DB_PATH + suffix)
            except FileNotFoundError:
                pass
        conn = sqlite3.connect(models.DB_PATH)
        conn.executescript('''
            CREATE TABLE user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT,
                email TEXT UNIQUE,
                is_admin BOOLEAN NOT NULL DEFAULT 0,
                is_banned BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE post (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE comment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO user (username, password, email)
                VALUES ('legacy', 'hash', 'legacy@example.com');
            INSERT INTO post (title, content, user_id)
                VALUES ('Legacy issue', 'Legacy content', 1);
            INSERT INTO comment (content, user_id, post_id)
                VALUES ('Legacy reply', 1, 1);
        ''')
        conn.commit()
        conn.close()

        init_db()

        conn = sqlite3.connect(models.DB_PATH)
        try:
            comment_columns = {
                row[1] for row in conn.execute('PRAGMA table_info(comment)')
            }
            self.assertIn('parent_id', comment_columns)
            self.assertIn('is_accepted', comment_columns)
            self.assertEqual(
                conn.execute('SELECT content FROM comment WHERE id = 1').fetchone()[0],
                'Legacy reply',
            )
        finally:
            conn.close()

    def test_post_author_controls_comment_acceptance(self):
        self.register('owner', 'owner@example.com')
        self.login('owner', 'secret1')
        self.client.post('/create', data={
            'title': 'First issue',
            'content': 'A sufficiently long issue body.',
        })
        self.logout()

        self.register('helper', 'helper@example.com', 'secret2')
        self.login('helper', 'secret2')
        self.client.post('/post/1', data={'content': 'A useful answer.'})
        response = self.client.post('/comment/1/accept')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.get_by_id(1).is_accepted)
        self.logout()

        self.login('owner', 'secret1')
        response = self.client.post('/comment/1/accept')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Comment.get_by_id(1).is_accepted)

    def test_comment_depth_limit_prevents_hidden_replies(self):
        self.register('person', 'person@example.com')
        user = User.get_by_username('person')
        post = Post(
            title='Nested issue', content='Long enough nested issue body',
            user_id=user.id, is_approved=True,
        ).save()
        parent_id = None
        for index in range(self.app.config['MAX_COMMENT_DEPTH'] + 1):
            parent_id = Comment(
                content=f'Reply {index}', user_id=user.id, post_id=post.id,
                parent_id=parent_id,
            ).save().id
        self.login('person', 'secret1')

        response = self.client.post(f'/post/{post.id}', data={
            'content': 'This reply must be rejected',
            'parent_id': parent_id,
        })

        self.assertEqual(response.status_code, 302)
        conn = sqlite3.connect(models.DB_PATH)
        try:
            self.assertEqual(
                conn.execute('SELECT COUNT(*) FROM comment').fetchone()[0],
                self.app.config['MAX_COMMENT_DEPTH'] + 1,
            )
        finally:
            conn.close()

    def test_deleting_parent_keeps_reply_thread_visible(self):
        self.register('person', 'person@example.com')
        user = User.get_by_username('person')
        post = Post(
            title='Thread issue', content='Long enough thread issue body',
            user_id=user.id, is_approved=True,
        ).save()
        parent = Comment(
            content='Parent reply', user_id=user.id, post_id=post.id,
        ).save()
        Comment(
            content='Child remains visible', user_id=user.id, post_id=post.id,
            parent_id=parent.id,
        ).save()
        parent.soft_delete(user.id)
        self.login('person', 'secret1')

        response = self.client.get(f'/post/{post.id}')
        self.assertIn('此评论已被删除'.encode(), response.data)
        self.assertIn(b'Child remains visible', response.data)

    def test_password_change_requires_current_password(self):
        self.register('person', 'person@example.com')
        self.login('person', 'secret1')

        response = self.client.post('/edit-profile', data={
            'username': 'person',
            'email': 'person@example.com',
            'password': 'newsecret',
            'password2': 'newsecret',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.get_by_username('person').check_password('secret1'))

    def test_mutations_reject_get_requests(self):
        self.login('admin', 'admin')
        for path in (
            '/logout',
            '/tourist-login',
            '/admin/user/2/unban',
            '/admin/user/2/promote/sub_admin',
            '/admin/user/2/demote',
            '/post/1/restore',
            '/comment/1/delete',
            '/comment/1/restore',
            '/comment/1/accept',
            '/comment/1/cancel-accept',
            '/admin/export-database',
        ):
            self.assertEqual(self.client.get(path).status_code, 405, path)

    def test_pending_tourist_posts_are_moderator_only(self):
        self.client.post('/tourist-login')
        self.client.post('/create', data={
            'title': 'Pending issue',
            'content': 'A pending tourist issue body.',
        })
        self.logout()

        self.register('person', 'person@example.com')
        self.login('person', 'secret1')
        self.assertEqual(self.client.get('/post/1').status_code, 404)
        response = self.client.get('/user/tourist')
        self.assertNotIn(b'Pending issue', response.data)

    def test_rejected_posts_remain_manageable(self):
        self.client.post('/tourist-login')
        self.client.post('/create', data={
            'title': 'Reviewable issue',
            'content': 'A tourist issue that can be reviewed again.',
        })
        self.logout()
        self.login('admin', 'admin')

        self.client.post('/post/1/reject')
        response = self.client.get('/admin/pending-posts?status=rejected')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Reviewable issue', response.data)

        self.client.post('/post/1/approve')
        self.assertTrue(Post.get_by_id(1).is_approved)
        self.logout()
        self.register('person', 'person@example.com')
        self.login('person', 'secret1')
        self.assertEqual(self.client.get('/post/1').status_code, 200)

    def test_templates_compile_and_main_pages_render(self):
        for template in self.app.jinja_env.list_templates():
            self.app.jinja_env.get_template(template)

        self.login('admin', 'admin')
        for path in ('/', '/admin/dashboard', '/admin/users', '/admin/settings'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

        response = self.client.get('/')
        self.assertIn(b'floating-add-btn', response.data)
        self.assertIn(b'href="/create"', response.data)

    def test_admin_cannot_remove_own_access(self):
        self.login('admin', 'admin')
        response = self.client.post('/admin/user/1/edit', data={
            'username': 'admin',
            'email': 'admin@example.com',
            'is_admin': '',
            'is_banned': 'y',
            'banned_reason': 'self ban attempt',
        })
        self.assertEqual(response.status_code, 302)
        admin = User.get_by_id(1)
        self.assertTrue(admin.is_admin)
        self.assertFalse(admin.is_banned)

        response = self.client.post('/admin/user/1/demote')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.get_by_id(1).is_admin)

    def test_tourist_account_cannot_gain_admin_permissions(self):
        self.login('admin', 'admin')
        response = self.client.post('/admin/user/2/promote/admin')
        self.assertEqual(response.status_code, 302)
        tourist = User.get_by_username('tourist')
        self.assertFalse(tourist.is_admin)
        self.assertFalse(tourist.is_sub_admin)

        self.client.post('/admin/user/2/edit', data={
            'username': 'tourist',
            'email': 'tourist@example.com',
            'is_admin': 'y',
        })
        tourist = User.get_by_username('tourist')
        self.assertFalse(tourist.is_admin)

    def test_disabling_tourist_access_ends_existing_session(self):
        self.client.post('/tourist-login')
        Settings.set('allow_tourist', 'false')

        response = self.client.get('/')

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/login'))

    def test_multiline_filter_escapes_html(self):
        self.register('person', 'person@example.com')
        user = User.get_by_username('person')
        post = Post(
            title='Escaping issue',
            content='<script>alert(1)</script>\nSecond line',
            user_id=user.id,
            is_approved=True,
        ).save()
        self.login('person', 'secret1')

        response = self.client.get(f'/post/{post.id}')
        self.assertNotIn(b'<script>alert(1)</script>', response.data)
        self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;<br>', response.data)

    def test_database_export_uses_a_valid_snapshot(self):
        self.login('admin', 'admin')
        response = self.client.post('/admin/export-database')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'SQLite format 3'))
        response.close()

    def test_csrf_is_enforced(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/login', data={
            'username': 'admin', 'password': 'admin'
        }).status_code, 400)

        response = self.client.get('/login')
        token = re.search(
            rb'name="csrf_token"[^>]*value="([^"]+)"', response.data
        ).group(1).decode()
        response = self.client.post('/login', data={
            'csrf_token': token,
            'username': 'admin',
            'password': 'admin',
        })
        self.assertEqual(response.status_code, 302)


if __name__ == '__main__':
    unittest.main()
