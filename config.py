import os

class Config:
    # 密钥配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    
    # 分页配置
    POSTS_PER_PAGE = 10 