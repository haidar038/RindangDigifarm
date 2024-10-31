import os
from datetime import timedelta
from flask import current_app
from flask_limiter.util import get_remote_address
from sqlalchemy import create_engine
from flask_limiter import Limiter
from dotenv import load_dotenv

load_dotenv()

# Use a default port if MYSQLPORT is not set
mysql_port = os.environ.get("MYSQLPORT", "3306")

mysql_uri = (f'mysql+pymysql://{os.environ.get("MYSQLUSER")}:'
        f'{os.environ.get("MYSQLPASSWORD")}@'
        f'{os.environ.get("MYSQLHOST")}:'
        f'{mysql_port}/'
        f'{os.environ.get("MYSQLDATABASE")}')

# Create engine only if all necessary environment variables are set
if all([os.environ.get("MYSQLUSER"), os.environ.get("MYSQLPASSWORD"),
        os.environ.get("MYSQLHOST"), os.environ.get("MYSQLDATABASE")]):
    engine = create_engine(mysql_uri)
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=f"mysql://{mysql_uri}",
        storage_options={"engine": engine}
    )
else:
    print("Warning: MySQL environment variables are not full")

class Config:
    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8082')
    SECRET_KEY = os.environ.get("SECRET_KEY", "rindang123")    
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')

    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or 'rindang_ternate_security_salt'
    SQLALCHEMY_DATABASE_URI = mysql_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_timeout": 20,
        "max_overflow": 5
    }
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # Batasi ukuran file (misal: 16MB)
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)  # Maksimum lifetime
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    CSRF_ENABLED = True
    CSRF_SECRET_KEY = "rindang_ternate_security_salt"

    # CKEDITOR CONFIGURATION
    CKEDITOR_PKG_TYPE = 'basic'
    CKEDITOR_ENABLE_CSRF = True
    CKEDITOR_SERVE_LOCAL = True

    # EMAIL CONFIGURATION
    MAIL_SERVER = 'srv175.niagahoster.com'
    MAIL_PORT = 465
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MAIL_USERNAME = os.environ.get('EMAIL_USER')
    MAIL_PASSWORD = os.environ.get('EMAIL_PASS')
    MAIL_DEFAULT_SENDER = os.environ.get('EMAIL_USER')
    MAIL_USE_CREDENTIALS = True
    MAIL_ASCII_ATTACHMENTS = False