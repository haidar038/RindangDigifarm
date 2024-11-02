import random, string, jwt

from time import time
from flask import current_app
from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from enum import Enum
from cryptography.fernet import Fernet

from App import db, admin, app

now = datetime.now()
key = Fernet.generate_key()
f = Fernet(key)

class UserRole(str, Enum):
    ADMIN = 'admin'
    PERSONAL = 'personal'
    AHLI = 'ahli'
    PETANI = 'petani'

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False, unique=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now())
    is_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    otp = db.Column(db.String(6))
    otp_created_at = db.Column(db.DateTime)
    
    # Shared profile data
    nama_lengkap = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    bio = db.Column(db.String(255), nullable=True)
    profile_pic = db.Column(db.String(255), nullable=True)
    
    # Add the relationships to profiles
    petani_profile = db.relationship('PetaniProfile', back_populates='user', uselist=False)
    ahli_profile = db.relationship('AhliProfile', back_populates='user', uselist=False)
    
    # Existing relationships
    kebun = db.relationship('Kebun', secondary='user_kebun', back_populates='users')
    roles = db.relationship('Role', secondary='user_roles', 
                            backref=db.backref('users', lazy='dynamic'))
    
    # Password handling
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute.')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_reset_password_token(self, expires_in=3600):
        """Generate a JWT token for password reset"""
        try:
            payload = {
                'reset_password': self.id,
                'exp': time() + expires_in
            }
            return jwt.encode(
                payload,
                current_app.config['SECRET_KEY'],
                algorithm='HS256'
            )
        except Exception as e:
            current_app.logger.error(f"Error generating reset token: {str(e)}")
            return None

    @staticmethod
    def verify_reset_password_token(token):
        """Verify the reset password token"""
        try:
            payload = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )
            return User.query.get(payload['reset_password'])
        except Exception as e:
            current_app.logger.error(f"Error verifying reset token: {str(e)}")
            return None

    def set_otp(self):
        """Generate and set new OTP"""
        self.otp = ''.join(random.choices(string.digits, k=6))
        self.otp_created_at = datetime.now()
        db.session.commit()

    def verify_otp(self, otp):
        """Verify OTP and check if it's still valid (10 minutes)"""
        if not self.otp or not self.otp_created_at:
            return False
        
        # Check if OTP is expired (10 minutes)
        if datetime.now() - self.otp_created_at > timedelta(minutes=10):
            return False
        
        return self.otp == otp

    @validates('email')
    def validate_email(self, key, address):
        assert '@' in address
        return address

    # Role checking methods
    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)

    def get_role_names(self):
        return [role.name for role in self.roles]

    def __repr__(self):
        return f"<User('{self.username}', '{self.email}')>"

class Admin(User):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    admin_level = db.Column(db.String(20), nullable=False, default='standard')

    __mapper_args__ = {
        'polymorphic_identity': 'admin'
    }

# Model untuk Role
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))

    def __repr__(self):
        return f"Role('{self.name}')"

# Tabel asosiasi untuk user-role many-to-many relationship
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id')),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'))
)

# PetaniProfile model
class PetaniProfile(db.Model):
    __tablename__ = 'petani_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    unique_id = db.Column(db.String(100), unique=True, nullable=False)
    luas_lahan = db.Column(db.Float, nullable=True)
    # Relationship back to User
    user = db.relationship('User', back_populates='petani_profile')

    def __repr__(self):
        return f"<PetaniProfile(User ID: {self.user_id})>"

# AhliProfile model
class AhliProfile(db.Model):
    __tablename__ = 'ahli_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    unique_id = db.Column(db.String(100), unique=True, nullable=False)
    institusi = db.Column(db.String(255), nullable=True)
    bidang_keahlian = db.Column(db.String(255), nullable=True)
    gelar = db.Column(db.String(100), nullable=True)
    # Relationship back to User
    user = db.relationship('User', back_populates='ahli_profile')

    def __repr__(self):
        return f"<AhliProfile(User ID: {self.user_id})>"

# Association Table untuk hubungan many-to-many dengan Kebun
user_kebun = db.Table('user_kebun',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id')),
    db.Column('kebun_id', db.Integer, db.ForeignKey('kebun.id'))
)

class Kebun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(20), nullable=True)
    nama = db.Column(db.String(255), nullable=True)
    foto = db.Column(db.String(100), nullable=True)
    luas_kebun = db.Column(db.Float, nullable=True)
    _koordinat = db.Column(db.LargeBinary, nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    pangan_data = db.relationship('DataPangan', backref='Kebun', lazy=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    users = db.relationship('User', secondary='user_kebun', back_populates='kebun')
    
    @property
    def koordinat(self):
        return f.decrypt(self._koordinat).decode() if self._koordinat else None
    
    @koordinat.setter
    def koordinat(self, value):
        self._koordinat = f.encrypt(value.encode())

    def __repr__(self):
        return f"Kebun('{self.nama}', ID: {self.unique_id})"

class Komoditas(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(255), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"Komoditas('{self.nama}')"

class DataPangan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    jml_bibit = db.Column(db.Integer, nullable=False)
    komoditas = db.Column(db.String(50), nullable=False)
    tanggal_bibit = db.Column(db.Date, nullable=False)
    jml_panen = db.Column(db.Integer, nullable=True, default=0)
    tanggal_panen = db.Column(db.Date, nullable=True)
    estimasi_panen = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=True, default='Penanaman')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    komoditas_id = db.Column(db.Integer, db.ForeignKey('komoditas.id', ondelete='SET NULL'), nullable=True)
    kebun_id = db.Column(db.Integer, db.ForeignKey('kebun.id', ondelete='CASCADE'), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"DataPangan(ID: {self.id}, Komoditas: {self.komoditas})"

class Artikel(db.Model):
    __tablename__ = 'artikel'
    id = db.Column(db.Integer, primary_key=True)
    thumbnail = db.Column(db.String(255), nullable=True)  # Thumbnail opsional
    judul = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now())
    is_approved = db.Column(db.Boolean, default=False)
    is_drafted = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"Artikel('{self.judul}', ID: {self.id})"

class Forum(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now())
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    replied_at = db.Column(db.DateTime, nullable=True)
    replied_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"Forum(ID: {self.id}, Question: {self.question[:20]}...)"

# Menambahkan Model UpgradeRequest
class UpgradeTypeEnum(Enum):
    PETANI = 'petani'
    AHLI = 'ahli'

class UpgradeRequest(db.Model):
    __tablename__ = 'upgrade_requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_role = db.Column(db.String(50), nullable=False)  # 'petani' atau 'ahli'
    reason = db.Column(db.Text, nullable=False)
    attachment = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now())
    updated_at = db.Column(db.DateTime, default=datetime.now(), onupdate=datetime.now())

    user = db.relationship('User', backref='upgrade_requests')

    def __repr__(self):
        return f"UpgradeRequest(User: {self.user.username}, Role: {self.requested_role}, Status: {self.status})"

class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.now())
    updated_at = db.Column(db.DateTime, default=datetime.now(), onupdate=datetime.now())

class SoftDeleteMixin:
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.now()