import io, os, logging

from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_toastr import Toastr
from flask import Flask
from flask_admin import Admin
from flask_sitemap import Sitemap
from flask_mail import Mail
from flask_flatpages import FlatPages
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_ckeditor import CKEditor
from flask_cors import CORS
from werkzeug.security import generate_password_hash
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from logging.handlers import RotatingFileHandler

from App.config import Config

app = Flask(__name__)

socketio = SocketIO(cors_allowed_origins="*")
db = SQLAlchemy()
login_manager = LoginManager()
toastr = Toastr()
admin = Admin(name='admin')
buffer = io.BytesIO()
migrate = Migrate(app, db)
ext = Sitemap()
mail = Mail()
ckeditor = CKEditor()
flatpages = FlatPages()
cache = Cache(config={'CACHE_TYPE': 'simple'})
limiter = Limiter(
    # Jangan set app di sini, gunakan init_app nanti
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"  # Gunakan memory storage untuk development
)

def seed_roles():
    from App.models import Role
    roles = [
        {'name': 'admin', 'description': 'Administrator sistem dengan akses penuh'},
        {'name': 'personal', 'description': 'Pengguna umum dengan akses dasar'},
        {'name': 'petani', 'description': 'Pengguna dengan peran petani'},
        {'name': 'ahli', 'description': 'Pengguna dengan peran ahli di bidang tertentu'},
    ]

    for role_data in roles:
        role = Role.query.filter_by(name=role_data['name']).first()
        if not role:
            role = Role(name=role_data['name'], description=role_data['description'])
            db.session.add(role)

def create_app(config_class=Config):
    app.config.from_object(config_class)
    db.init_app(app)
    socketio.init_app(app)
    login_manager.init_app(app)
    toastr.init_app(app)
    ckeditor.init_app(app)
    flatpages.init_app(app)
    mail.init_app(app)
    ext.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    login_manager.login_view = 'auth.login'
    login_manager.login_message = "Anda harus melakukan login terlebih dahulu"
    login_manager.login_message_category = "warning"

    from App.routes.auth_routes import auth
    from App.routes.admin_routes import admin
    from App.routes.farmer_routes import farmer
    from App.routes.expert_routes import expert
    from App.routes.personal_routes import personal
    from App.routes.public_routes import public
    app.register_blueprint(auth, url_prefix='/auth/login')
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(farmer, url_prefix='/petani')
    app.register_blueprint(expert, url_prefix='/ahli')
    app.register_blueprint(personal, url_prefix='/personal')
    app.register_blueprint(public, url_prefix='/')
    
    if not os.path.exists('logs'):
        os.makedirs('logs')

    file_handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=1024 * 1024,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Rindang startup')

    with app.app_context():
        db.create_all()
        seed_roles()

        from App.models import User, Role # Ganti import Admin menjadi User

        # Ensure the upload folder exists
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        # Cek apakah admin sudah ada
        admin = User.query.filter_by(username='admin').first()
        admin_role = Role.query.filter_by(name='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='official@rindang.net',
                password=generate_password_hash('admrindang123'),
            )
            admin.is_confirmed = True
            admin.roles.append(admin_role)
            db.session.add(admin)
            db.session.commit()

        db.session.commit()
        print('Roles configuration complete')

        # try:
        #     with mail.connect() as conn:
        #         print("Email configuration is correct and connection successful")
        # except Exception as e:
        #     print(f"Error in email configuration: {str(e)}")

    return app