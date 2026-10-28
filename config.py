import os
import secrets
from datetime import timedelta
from pathlib import Path


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _load_or_create_secret_key():
    """Load a stable secret key, creating a mode-0600 local key if needed."""
    configured = os.environ.get('SECRET_KEY', '').strip()
    if configured:
        if len(configured) < 32:
            raise RuntimeError('SECRET_KEY 必须至少为 32 个字符。')
        return configured

    db_dir = Path(os.environ.get('DB_DIR') or Path(__file__).resolve().parent)
    secret_file = Path(os.environ.get('SECRET_KEY_FILE') or db_dir / '.secret_key')
    try:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        if secret_file.exists():
            if secret_file.is_symlink() or not secret_file.is_file():
                raise RuntimeError(f'SECRET_KEY_FILE {secret_file} 必须是普通文件，不能是符号链接。')
            value = secret_file.read_text(encoding='utf-8').strip()
            if len(value) < 32:
                raise RuntimeError(
                    f'SECRET_KEY_FILE {secret_file} 内容过短；请删除该文件让程序重建，'
                    '或显式设置至少 32 字符的 SECRET_KEY。'
                )
            try:
                secret_file.chmod(0o600)
            except OSError:
                pass
            return value

        value = secrets.token_hex(32)
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(value + '\n')
        return value
    except FileExistsError:
        # Another worker/process won the creation race. Re-read the shared key.
        if secret_file.is_symlink() or not secret_file.is_file():
            raise RuntimeError(f'SECRET_KEY_FILE {secret_file} 必须是普通文件。')
        value = secret_file.read_text(encoding='utf-8').strip()
        if len(value) < 32:
            raise RuntimeError(f'SECRET_KEY_FILE {secret_file} 内容无效。')
        return value
    except OSError as exc:
        raise RuntimeError(
            '未设置 SECRET_KEY，且无法在 DB_DIR 中持久化会话密钥。'
            '请设置 SECRET_KEY 或确保 DB_DIR 可写。'
        ) from exc


class Config:
    SECRET_KEY = _load_or_create_secret_key()
    POSTS_PER_PAGE = 10
    USERS_PER_PAGE = 10
    MAX_COMMENT_DEPTH = 5

    # Bound request parsing before WTForms validation to reduce memory/CPU abuse.
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 1024 * 1024))
    MAX_FORM_MEMORY_SIZE = int(os.environ.get('MAX_FORM_MEMORY_SIZE', 256 * 1024))
    MAX_FORM_PARTS = int(os.environ.get('MAX_FORM_PARTS', 64))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _env_bool('COOKIE_SECURE', False)
    SESSION_COOKIE_NAME = 'feedback_session'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = _env_bool('COOKIE_SECURE', False)
    REMEMBER_COOKIE_DURATION = timedelta(days=14)

    WTF_CSRF_TIME_LIMIT = 3600

    _trusted_hosts = [
        host.strip() for host in os.environ.get('TRUSTED_HOSTS', '').split(',')
        if host.strip()
    ]
    TRUSTED_HOSTS = _trusted_hosts or None
