import os
import re
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

# Keep test imports deterministic and avoid creating a project-local secret file.
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-feedback-platform-1234567890')

import models
from app import create_app
from models import Comment, Post, Settings, User, init_db


ADMIN_PASSWORD = 'AuditAdminPass!123'
USER_PASSWORD = 'secret123'
SECOND_PASSWORD = 'secret234'


class FeedbackPlatformTestCase(unittest.TestCase):
    def setUp(self):
        self.original_admin_password = os.environ.get('ADMIN_PASSWORD')
        os.environ['ADMIN_PASSWORD'] = ADMIN_PASSWORD
        self.temp_dir = tempfile.mkdtemp()
        models.db_dir = self.temp_dir
        models.DB_PATH = os.path.join(self.temp_dir, 'feedback.db')
        self.app = create_app()
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = self.app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self.original_admin_password is None:
            os.environ.pop('ADMIN_PASSWORD', None)
        else:
            os.environ['ADMIN_PASSWORD'] = self.original_admin_password

    def register(self, username, email, password='secret123'):
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
        user.set_password('secret123')
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

    def test_very_old_database_missing_base_columns_still_starts(self):
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
                email TEXT UNIQUE
            );
            CREATE TABLE post (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                user_id INTEGER NOT NULL
            );
            CREATE TABLE comment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL
            );
            INSERT INTO user (username, password, email) VALUES ('old', 'hash', 'old@example.com');
            INSERT INTO post (title, content, user_id) VALUES ('Old issue', 'Old content', 1);
            INSERT INTO comment (content, user_id, post_id) VALUES ('Old reply', 1, 1);
        ''')
        conn.commit()
        conn.close()

        init_db()

        conn = sqlite3.connect(models.DB_PATH)
        try:
            user_columns = {row[1] for row in conn.execute('PRAGMA table_info(user)')}
            post_columns = {row[1] for row in conn.execute('PRAGMA table_info(post)')}
            comment_columns = {row[1] for row in conn.execute('PRAGMA table_info(comment)')}
            self.assertTrue({'is_admin', 'created_at', 'auth_version'} <= user_columns)
            self.assertTrue({'created_at', 'is_pinned', 'is_approved'} <= post_columns)
            self.assertTrue({'created_at', 'parent_id', 'is_accepted'} <= comment_columns)
            self.assertIsNotNone(
                conn.execute('SELECT created_at FROM post WHERE id = 1').fetchone()[0]
            )
            self.assertEqual(
                conn.execute('SELECT is_admin FROM user WHERE id = 1').fetchone()[0], 0
            )
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            conn.close()

    def test_legacy_empty_emails_are_normalized_before_unique_index(self):
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
                email TEXT,
                is_admin BOOLEAN NOT NULL DEFAULT 0,
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
            INSERT INTO user (username, password, email) VALUES ('a', 'h', '');
            INSERT INTO user (username, password, email) VALUES ('b', 'h', '   ');
            INSERT INTO user (username, password, email) VALUES ('c', 'h', NULL);
            INSERT INTO user (username, password, email) VALUES ('d', 'h', 'real@example.com');
        ''')
        conn.commit()
        conn.close()

        init_db()

        conn = sqlite3.connect(models.DB_PATH)
        try:
            emails = [row[0] for row in conn.execute('SELECT email FROM user WHERE id <= 3')]
            self.assertEqual(emails, [None, None, None])
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO user (username, email) VALUES ('dupe1', 'case@example.com')")
                conn.execute("INSERT INTO user (username, email) VALUES ('dupe2', 'CASE@example.com')")
            conn.rollback()
        finally:
            conn.close()

    def test_healthz_returns_503_when_database_is_unavailable(self):
        with patch('app.get_db_connection', side_effect=OSError('disk unavailable')):
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()['status'], 'error')

    def test_user_profile_url_is_case_insensitive(self):
        self.register('ProfileCase', 'profilecase@example.com')
        self.login('ProfileCase', USER_PASSWORD)
        self.assertEqual(self.client.get('/user/profilecase').status_code, 200)
        self.assertEqual(self.client.get('/user/PROFILECASE').status_code, 200)

    def test_anonymous_unknown_url_returns_404(self):
        response = self.client.get('/definitely-not-a-page')
        self.assertEqual(response.status_code, 404)

    def test_anonymous_post_detail_redirects_to_login(self):
        response = self.client.get('/post/1')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers['Location'])

    def test_post_author_controls_comment_acceptance(self):
        self.register('owner', 'owner@example.com')
        self.login('owner', 'secret123')
        self.client.post('/create', data={
            'title': 'First issue',
            'content': 'A sufficiently long issue body.',
        })
        self.logout()

        self.register('helper', 'helper@example.com', 'secret234')
        self.login('helper', 'secret234')
        self.client.post('/post/1', data={'content': 'A useful answer.'})
        response = self.client.post('/comment/1/accept')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.get_by_id(1).is_accepted)
        self.logout()

        self.login('owner', 'secret123')
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
        self.login('person', 'secret123')

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
        self.login('person', 'secret123')

        response = self.client.get(f'/post/{post.id}')
        self.assertIn('此评论已被删除'.encode(), response.data)
        self.assertIn(b'Child remains visible', response.data)

    def test_password_change_requires_current_password(self):
        self.register('person', 'person@example.com')
        self.login('person', 'secret123')

        response = self.client.post('/edit-profile', data={
            'username': 'person',
            'email': 'person@example.com',
            'password': 'newsecret',
            'password2': 'newsecret',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.get_by_username('person').check_password('secret123'))

    def test_mutations_reject_get_requests(self):
        self.login('admin', ADMIN_PASSWORD)
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
        self.login('person', 'secret123')
        self.assertEqual(self.client.get('/post/1').status_code, 404)
        response = self.client.get('/user/tourist')
        self.assertNotIn(b'Pending issue', response.data)

    def test_pending_tourist_post_visible_to_author(self):
        self.client.post('/tourist-login')
        self.client.post('/create', data={
            'title': 'Author visible issue',
            'content': 'A pending tourist issue visible to its author.',
        })
        response = self.client.get('/post/1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Author visible issue', response.data)

    def test_rejected_posts_remain_manageable(self):
        self.client.post('/tourist-login')
        self.client.post('/create', data={
            'title': 'Reviewable issue',
            'content': 'A tourist issue that can be reviewed again.',
        })
        self.logout()
        self.login('admin', ADMIN_PASSWORD)

        self.client.post('/post/1/reject')
        response = self.client.get('/admin/pending-posts?status=rejected')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Reviewable issue', response.data)

        self.client.post('/post/1/approve')
        self.assertTrue(Post.get_by_id(1).is_approved)
        self.logout()
        self.register('person', 'person@example.com')
        self.login('person', 'secret123')
        self.assertEqual(self.client.get('/post/1').status_code, 200)

    def test_edit_profile_updates_account_and_rejects_reserved_names(self):
        self.register('editor', 'editor@example.com')
        self.login('editor', USER_PASSWORD)
        self.assertEqual(self.client.get('/edit-profile').status_code, 200)

        response = self.client.post('/edit-profile', data={
            'username': 'editor2',
            'email': 'editor2@example.com',
            'current_password': '',
            'password': '',
            'password2': '',
        })
        self.assertEqual(response.status_code, 302)
        updated = User.get_by_username('editor2')
        self.assertIsNotNone(updated)
        self.assertEqual(updated.email, 'editor2@example.com')

        response = self.client.post('/edit-profile', data={
            'username': 'admin',
            'email': 'editor2@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(User.get_by_username('editor2'))

        response = self.client.post('/edit-profile', data={
            'username': 'editor2',
            'email': 'editor2@example.com',
            'current_password': USER_PASSWORD,
            'password': SECOND_PASSWORD,
            'password2': SECOND_PASSWORD,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/login'))
        self.assertTrue(User.get_by_username('editor2').check_password(SECOND_PASSWORD))

    def test_admin_settings_update_takes_effect(self):
        self.login('admin', ADMIN_PASSWORD)
        response = self.client.post('/admin/settings', data={
            'platform_name': '新反馈平台',
            'allow_tourist': 'on',
            'allow_tourist_comment': 'on',
            'timezone': 'America/New_York',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Settings.get('platform_name'), '新反馈平台')
        self.assertEqual(Settings.get('timezone'), 'America/New_York')
        self.assertIn('新反馈平台'.encode(), self.client.get('/').data)

        self.client.post('/admin/settings', data={
            'platform_name': '不应生效',
            'timezone': 'Not/AZone',
        })
        self.assertEqual(Settings.get('platform_name'), '新反馈平台')

    def test_sub_admin_scope_is_limited_to_regular_users(self):
        normal = User(username='managed', email='managed@example.com')
        normal.set_password(USER_PASSWORD)
        normal.save()
        sub = User(username='submod', email='submod@example.com')
        sub.set_password(SECOND_PASSWORD)
        sub.save()
        sub.promote_to_sub_admin()

        self.login('submod', SECOND_PASSWORD)
        self.assertEqual(self.client.get('/admin/users').status_code, 200)
        self.assertEqual(self.client.get(f'/admin/user/{normal.id}/edit').status_code, 200)
        self.assertEqual(self.client.get('/admin/settings').status_code, 302)
        self.assertEqual(self.client.get('/admin/user/1/edit').status_code, 302)

    def test_templates_compile_and_main_pages_render(self):
        for template in self.app.jinja_env.list_templates():
            self.app.jinja_env.get_template(template)

        self.login('admin', ADMIN_PASSWORD)
        for path in ('/', '/admin/dashboard', '/admin/users', '/admin/settings'):
            self.assertEqual(self.client.get(path).status_code, 200, path)

        response = self.client.get('/')
        self.assertIn(b'floating-add-btn', response.data)
        self.assertIn(b'href="/create"', response.data)

    def test_admin_cannot_remove_own_access(self):
        self.login('admin', ADMIN_PASSWORD)
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
        self.login('admin', ADMIN_PASSWORD)
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
        self.login('person', 'secret123')

        response = self.client.get(f'/post/{post.id}')
        self.assertNotIn(b'<script>alert(1)</script>', response.data)
        self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;<br>', response.data)

    def test_database_export_uses_a_valid_snapshot(self):
        self.login('admin', ADMIN_PASSWORD)
        response = self.client.post('/admin/export-database')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'SQLite format 3'))
        response.close()

    def test_sub_admin_cannot_manage_peer_sub_admin(self):
        first = User(username='subone', email='subone@example.com', is_sub_admin=True)
        first.set_password('secret123')
        first.save()
        second = User(username='subtwo', email='subtwo@example.com', is_sub_admin=True)
        second.set_password('secret234')
        second.save()

        self.login('subone', 'secret123')

        response = self.client.post(f'/admin/user/{second.id}/edit', data={
            'username': 'subtwo-hijacked',
            'email': 'subtwo@example.com',
            'is_banned': 'y',
            'banned_reason': 'peer modification attempt',
        })
        self.assertEqual(response.status_code, 302)
        unchanged = User.get_by_id(second.id)
        self.assertEqual(unchanged.username, 'subtwo')
        self.assertFalse(unchanged.is_banned)

        response = self.client.post(f'/admin/user/{second.id}/unban')
        self.assertEqual(response.status_code, 403)

    def test_deleted_post_cannot_be_pinned_or_accept_comment(self):
        self.register('owner2', 'owner2@example.com')
        owner = User.get_by_username('owner2')
        post = Post(
            title='Deleted issue', content='Long enough deleted issue body',
            user_id=owner.id, is_approved=True,
        ).save()
        helper = User(username='helper2', email='helper2@example.com')
        helper.set_password('secret234')
        helper.save()
        comment = Comment(
            content='Useful but archived reply', user_id=helper.id, post_id=post.id,
        ).save()
        post.soft_delete(owner.id)

        self.login('admin', ADMIN_PASSWORD)
        self.client.post(f'/post/{post.id}/pin')
        self.assertFalse(Post.get_by_id(post.id).is_pinned)
        self.client.post(f'/comment/{comment.id}/accept')
        self.assertFalse(Comment.get_by_id(comment.id).is_accepted)


    def test_fresh_database_requires_explicit_admin_password(self):
        for suffix in ('', '-wal', '-shm'):
            try:
                os.remove(models.DB_PATH + suffix)
            except FileNotFoundError:
                pass
        os.environ.pop('ADMIN_PASSWORD', None)
        with self.assertRaisesRegex(RuntimeError, 'ADMIN_PASSWORD'):
            init_db()
        os.environ['ADMIN_PASSWORD'] = 'too-short'
        with self.assertRaisesRegex(RuntimeError, '12'):
            init_db()
        os.environ['ADMIN_PASSWORD'] = ADMIN_PASSWORD
        init_db()

    def test_password_change_invalidates_existing_sessions(self):
        self.register('personx', 'personx@example.com')
        self.login('personx', 'secret123')
        response = self.client.post('/edit-profile', data={
            'username': 'personx', 'email': 'personx@example.com',
            'current_password': 'secret123', 'password': 'newsecret',
            'password2': 'newsecret',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/login'))
        self.assertFalse(User.get_by_username('personx').check_password('secret123'))
        self.assertTrue(User.get_by_username('personx').check_password('newsecret'))

    def test_reserved_and_case_conflicting_usernames_are_rejected(self):
        response = self.register('Admin', 'admin2@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(User.get_by_username('Admin'))
        self.register('PersonCase', 'case1@example.com')
        response = self.register('personcase', 'case2@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(User.get_by_username('personcase'))

    def test_database_enforces_case_insensitive_username_uniqueness(self):
        first = User(username='MixedCase', email='mixed1@example.com')
        first.set_password('secret123')
        first.save()
        second = User(username='mixedcase', email='mixed2@example.com')
        second.set_password('secret234')
        with self.assertRaises(sqlite3.IntegrityError):
            second.save()

    def test_deleting_accepted_comment_revokes_acceptance(self):
        owner = User(username='ownerx', email='ownerx@example.com')
        owner.set_password('secret123'); owner.save()
        post = Post(title='Acceptance issue', content='Long enough acceptance issue body', user_id=owner.id, is_approved=True).save()
        comment = Comment(content='Accepted answer', user_id=owner.id, post_id=post.id).save()
        comment.accept(owner.id)
        comment.soft_delete(owner.id)
        deleted = Comment.get_by_id(comment.id)
        self.assertTrue(deleted.is_deleted)
        self.assertFalse(deleted.is_accepted)
        self.assertIsNone(deleted.accepted_by)

    def test_database_enforces_one_active_accepted_comment_per_post(self):
        owner = User(username='owneruniq', email='owneruniq@example.com')
        owner.set_password('secret123'); owner.save()
        post = Post(title='Unique accepted', content='Long enough unique accepted body', user_id=owner.id, is_approved=True).save()
        first = Comment(content='First answer', user_id=owner.id, post_id=post.id).save()
        second = Comment(content='Second answer', user_id=owner.id, post_id=post.id).save()
        first.accept(owner.id)
        conn = sqlite3.connect(models.DB_PATH)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('UPDATE comment SET is_accepted = 1, accepted_by = ? WHERE id = ?', (owner.id, second.id))
                conn.commit()
        finally:
            conn.rollback(); conn.close()

    def test_dynamic_pages_have_security_headers_and_health(self):
        response = self.client.get('/login')
        self.assertEqual(response.headers['Cache-Control'], 'no-store, private')
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        health = self.client.get('/healthz')
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {'status': 'ok'})

    def test_system_admin_model_invariant(self):
        admin = User.get_by_username('admin')
        admin.is_admin = False
        admin.is_sub_admin = True
        admin.is_banned = True
        admin.banned_reason = 'should not persist'
        admin.save()
        admin = User.get_by_username('admin')
        self.assertTrue(admin.is_admin)
        self.assertFalse(admin.is_sub_admin)
        self.assertFalse(admin.is_banned)

    def test_tourist_model_guard(self):
        tourist = User.get_by_username('tourist')
        with self.assertRaises(ValueError):
            tourist.promote_to_admin()
        with self.assertRaises(ValueError):
            tourist.promote_to_sub_admin()

    def test_username_rejects_route_breaking_characters(self):
        response = self.register('bad/name', 'badname@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(User.get_by_username('bad/name'))

    def test_database_rejects_cross_post_parent_comment(self):
        owner = User(username='triggerowner', email='triggerowner@example.com')
        owner.set_password(USER_PASSWORD)
        owner.save()
        first_post = Post(title='Trigger one', content='Long enough trigger body one', user_id=owner.id, is_approved=True).save()
        second_post = Post(title='Trigger two', content='Long enough trigger body two', user_id=owner.id, is_approved=True).save()
        parent = Comment(content='Parent on first', user_id=owner.id, post_id=first_post.id).save()
        conn = sqlite3.connect(models.DB_PATH)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    'INSERT INTO comment (content, user_id, post_id, parent_id) VALUES (?, ?, ?, ?)',
                    ('Invalid cross-post reply', owner.id, second_post.id, parent.id),
                )
                conn.commit()
        finally:
            conn.rollback()
            conn.close()

    def test_pending_tourist_post_cannot_be_pinned_or_accepted(self):
        owner = User(username='pendingowner', email='pendingowner@example.com')
        owner.set_password(USER_PASSWORD)
        owner.save()
        pending = Post(
            title='Pending guarded', content='Long enough pending guarded body', user_id=owner.id,
            is_tourist_post=True, is_approved=None,
        ).save()
        comment = Comment(content='Pending answer', user_id=owner.id, post_id=pending.id).save()
        self.login('admin', ADMIN_PASSWORD)
        self.client.post(f'/post/{pending.id}/pin')
        self.client.post(f'/comment/{comment.id}/accept')
        self.assertFalse(Post.get_by_id(pending.id).is_pinned)
        self.assertFalse(Comment.get_by_id(comment.id).is_accepted)

    def test_deleting_or_rejecting_post_clears_pin(self):
        owner = User(username='pinowner', email='pinowner@example.com')
        owner.set_password(USER_PASSWORD)
        owner.save()
        normal = Post(title='Pinned normal', content='Long enough pinned normal body', user_id=owner.id, is_approved=True).save()
        normal.pin()
        normal.soft_delete(owner.id)
        self.assertFalse(Post.get_by_id(normal.id).is_pinned)

        tourist = Post(
            title='Pinned tourist', content='Long enough pinned tourist body', user_id=owner.id,
            is_tourist_post=True, is_approved=True,
        ).save()
        tourist.pin()
        tourist.reject()
        reloaded = Post.get_by_id(tourist.id)
        self.assertFalse(reloaded.is_pinned)
        self.assertFalse(reloaded.is_approved)

    def test_request_body_limit_and_csp_header(self):
        response = self.client.get('/login')
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        original_limit = self.app.config['MAX_CONTENT_LENGTH']
        self.app.config['MAX_CONTENT_LENGTH'] = 128
        try:
            response = self.client.post('/login', data={
                'username': 'u' * 300,
                'password': USER_PASSWORD,
            })
            self.assertEqual(response.status_code, 413)
        finally:
            self.app.config['MAX_CONTENT_LENGTH'] = original_limit

    def test_hiding_post_revokes_existing_acceptance(self):
        owner = User(username='stateowner', email='stateowner@example.com')
        owner.set_password(USER_PASSWORD)
        owner.save()
        helper = User(username='statehelper', email='statehelper@example.com')
        helper.set_password(SECOND_PASSWORD)
        helper.save()

        normal = Post(
            title='Accepted then deleted', content='Long enough accepted state body',
            user_id=owner.id, is_approved=True,
        ).save()
        normal_comment = Comment(
            content='Accepted before delete', user_id=helper.id, post_id=normal.id,
        ).save()
        normal_comment.accept(owner.id)
        normal.soft_delete(owner.id)
        self.assertFalse(Comment.get_by_id(normal_comment.id).is_accepted)

        tourist = Post(
            title='Accepted then rejected', content='Long enough tourist state body',
            user_id=owner.id, is_tourist_post=True, is_approved=True,
        ).save()
        tourist_comment = Comment(
            content='Accepted before reject', user_id=helper.id, post_id=tourist.id,
        ).save()
        tourist_comment.accept(owner.id)
        tourist.reject()
        self.assertFalse(Comment.get_by_id(tourist_comment.id).is_accepted)

    def test_database_enforces_system_role_invariants(self):
        admin = User.get_by_username('admin')
        tourist = User.get_by_username('tourist')
        conn = sqlite3.connect(models.DB_PATH)
        try:
            for sql, params in (
                ('UPDATE user SET is_admin = 0 WHERE id = ?', (admin.id,)),
                ('UPDATE user SET is_sub_admin = 1 WHERE id = ?', (admin.id,)),
                ('UPDATE user SET is_admin = 1 WHERE id = ?', (tourist.id,)),
            ):
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute(sql, params)
                    conn.commit()
                conn.rollback()
        finally:
            conn.close()

    def test_login_username_is_case_insensitive(self):
        self.register('CaseLogin', 'caselogin@example.com')
        response = self.login('caselogin', USER_PASSWORD)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/index'))

    def test_external_login_redirect_is_rejected(self):
        self.register('redirectuser', 'redirect@example.com')
        response = self.client.post(
            '/login?next=https://example.invalid/phish',
            data={'username': 'redirectuser', 'password': USER_PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/index'))

    def test_activity_log_failure_does_not_repeat_completed_action(self):
        self.register('loggeruser', 'logger@example.com')
        self.login('loggeruser', USER_PASSWORD)
        with patch('app.ActivityLog.create_log', side_effect=sqlite3.OperationalError('locked')):
            response = self.client.post('/create', data={
                'title': 'Action survives log failure',
                'content': 'This action should remain successful when audit storage is busy.',
            })
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(Post.get_by_id(1))

    def test_csrf_is_enforced(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post('/login', data={
            'username': 'admin', 'password': ADMIN_PASSWORD
        }).status_code, 400)

        response = self.client.get('/login')
        token = re.search(
            rb'name="csrf_token"[^>]*value="([^"]+)"', response.data
        ).group(1).decode()
        response = self.client.post('/login', data={
            'csrf_token': token,
            'username': 'admin',
            'password': ADMIN_PASSWORD,
        })
        self.assertEqual(response.status_code, 302)


if __name__ == '__main__':
    unittest.main()
