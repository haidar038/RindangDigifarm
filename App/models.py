import random, string, jwt

from time import time
from flask import current_app
from flask_login import UserMixin
from sqlalchemy import orm
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from enum import Enum
from cryptography.fernet import Fernet

from App import db

now = datetime.now()
key = Fernet.generate_key()
f = Fernet(key)

class UserRole(str, Enum):
    ADMIN = 'admin'
    PERSONAL = 'personal'
    AHLI = 'ahli'
    PETANI = 'petani'

class QueryWithSoftDelete(orm.Query):
    def get(self, *args, **kwargs):
        # Include condition to filter soft-deleted records
        return super().filter_by(is_deleted=False).get(*args, **kwargs)

    def __iter__(self):
        # Include condition to filter soft-deleted records in iteration
        return super().filter_by(is_deleted=False).__iter__()

    def with_deleted(self):
        # Return unfiltered query
        return self

    def without_deleted(self):
        # Return filtered query
        return self.filter_by(is_deleted=False)

    def _get(self, *args, **kwargs):
        # Include default filter in base query
        return super().filter_by(is_deleted=False)._get(*args, **kwargs)

    def update(self, values):
        # Preserve normal update behavior
        return super().update(values)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    # Core fields
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), nullable=False, unique=True)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password = db.Column(db.String(255), nullable=False)
    
    # Status fields
    is_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    # OTP fields
    otp = db.Column(db.String(6))
    otp_created_at = db.Column(db.DateTime)
    
    # Profile fields  
    nama_lengkap = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    pekerjaan = db.Column(db.String(128))
    bio = db.Column(db.String(255))
    profile_pic = db.Column(db.String(255))
    kec = db.Column(db.String(255))
    kota = db.Column(db.String(255))
    kelurahan = db.Column(db.String(255))
    
    # Relationships
    petani_profile = db.relationship('PetaniProfile', back_populates='user', uselist=False, 
                                    cascade='all, delete-orphan')
    ahli_profile = db.relationship('AhliProfile', back_populates='user', uselist=False,
                                    cascade='all, delete-orphan')
    kebun = db.relationship('Kebun', backref='user', lazy=True, cascade='all, delete-orphan')
    roles = db.relationship('Role', secondary='user_roles', 
                            backref=db.backref('users', lazy='dynamic'),
                            lazy='joined')
                            
    # Query Class
    query_class = QueryWithSoftDelete

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if not any(role.name == 'personal' for role in self.roles):
            personal_role = Role.query.filter_by(name='personal').first()
            if personal_role:
                self.roles.append(personal_role)

    def get_reset_password_token(self, expires_in=3600):
        try:
            return jwt.encode(
                {'reset_password': self.id, 'exp': time() + expires_in},
                current_app.config['SECRET_KEY'],
                algorithm='HS256'
            )
        except Exception as e:
            current_app.logger.error(f"Token generation error: {e}")
            return None

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'], 
                            algorithms=['HS256'])['reset_password']
            return User.query.get(id)
        except Exception as e:
            current_app.logger.error(f"Token verification error: {e}")
            return None

    def set_otp(self):
        self.otp = ''.join(random.choices(string.digits, k=6))
        self.otp_created_at = datetime.utcnow()
        db.session.commit()

    def verify_otp(self, otp):
        if not self.otp or not self.otp_created_at:
            return False
        if datetime.utcnow() - self.otp_created_at > timedelta(minutes=10):
            return False
        return self.otp == otp

    @validates('email')
    def validate_email(self, key, address):
        if not '@' in address:
            raise ValueError('Invalid email address')
        return address

    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)

    def get_role_names(self):
        return [role.name for role in self.roles]

    def soft_delete(self):
        """Soft delete the user and associated records"""
        self.is_deleted = True 
        self.deleted_at = datetime.utcnow()
        # Soft delete associated records if needed
        for kebun in self.kebun:
            kebun.soft_delete()
        db.session.commit()
    
    def restore(self):
        """Restore a soft-deleted user"""
        self.is_deleted = False
        self.deleted_at = None
        db.session.commit()

    @classmethod
    def get_active_users(cls):
        return cls.query.all()

    @classmethod 
    def get_all_including_deleted(cls):
        return cls.query.with_deleted().all()

    @classmethod
    def get_only_deleted(cls):
        return cls.query.filter_by(is_deleted=True).all()

    def __repr__(self):
        return f"<User {self.username}>"

# Tabel asosiasi untuk user-role many-to-many relationship
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id')),
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'))
)

# Model untuk Role
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))

    # Use dynamic relationship to avoid type checking issues
    # users = db.relationship('User', secondary=user_roles, 
    #                         backref=db.backref('roles', lazy='dynamic'), 
    #                         lazy='dynamic')

    def __repr__(self):
        return f"Role('{self.name}')"

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

class Komoditas(db.Model):
    """Master data of commodity types"""
    __tablename__ = 'komoditas'
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(255), nullable=False)
    kategori = db.Column(db.String(255), nullable=False)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now())
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    # Relationships
    kebun_komoditas = db.relationship('KebunKomoditas', 
                                    back_populates='komoditas',
                                    cascade="all, delete-orphan")
    data_pangan = db.relationship('DataPangan', 
                                back_populates='komoditas_info',
                                cascade="all, delete-orphan")

    def __repr__(self):
        return f"Komoditas('{self.nama}', Kategori: '{self.kategori}')"

class KebunKomoditas(db.Model):
    """Junction table between Kebun and Komoditas with status tracking"""
    __tablename__ = 'kebun_komoditas'
    id = db.Column(db.Integer, primary_key=True)
    kebun_id = db.Column(db.Integer, db.ForeignKey('kebun.id', ondelete='CASCADE'), nullable=False)
    komoditas_id = db.Column(db.Integer, db.ForeignKey('komoditas.id', ondelete='CASCADE'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    luas_tanam = db.Column(db.Float, nullable=True)  # Tambahan: luas area untuk komoditas ini
    added_at = db.Column(db.DateTime, default=datetime.now())
    deactivated_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    kebun = db.relationship('Kebun', back_populates='kebun_komoditas')
    komoditas = db.relationship('Komoditas', back_populates='kebun_komoditas')

    def deactivate(self):
        """Deactivate this commodity in the garden"""
        self.is_active = False
        self.deactivated_at = datetime.now()

class Kebun(db.Model):
    """Gardens that can grow multiple commodities"""
    __tablename__ = 'kebun'
    id = db.Column(db.Integer, primary_key=True)
    unique_id = db.Column(db.String(20), unique=True, nullable=False)
    nama = db.Column(db.String(255), nullable=False)
    foto = db.Column(db.Text, nullable=True)
    komoditas = db.Column(db.String(255), nullable=False)  # Untuk menyimpan list komoditas yang dipisahkan koma
    luas_kebun = db.Column(db.Float, nullable=True)
    koordinat = db.Column(db.String(100), nullable=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now())
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Relationships
    kebun_komoditas = db.relationship('KebunKomoditas', 
                                    back_populates='kebun',
                                    cascade="all, delete-orphan")
    data_pangan = db.relationship('DataPangan', 
                                back_populates='kebun',
                                cascade="all, delete-orphan")
    users = db.relationship('User', 
                            secondary='user_kebun',
                            back_populates='kebun')

    @property
    def active_komoditas(self):
        """Get all active commodities in this garden"""
        return [kk.komoditas for kk in self.kebun_komoditas.filter_by(is_active=True)]

    @property
    def foto_list(self):
        """Return list of photos"""
        return self.foto.split(',') if self.foto else []
    
    @foto_list.setter 
    def foto_list(self, photos):
        """Set photos as comma-separated string"""
        self.foto = ','.join(photos) if photos else None

    def should_be_deleted(self):
        """Check if the Kebun should be permanently deleted."""
        if self.is_deleted and self.deleted_at:
            return datetime.now() > self.deleted_at + timedelta(days=30)
        return False

    def __repr__(self):
        return f"Kebun('{self.nama}', ID: {self.unique_id}, Luas: {self.luas_kebun})"

def delete_old_soft_deleted_kebun():
    """Delete Kebun data that has been soft deleted for more than 30 days."""
    old_kebuns = Kebun.query.filter(Kebun.is_deleted == True).all()
    for kebun in old_kebuns:
        if kebun.should_be_deleted():
            db.session.delete(kebun)
    db.session.commit()

class DataPangan(db.Model):
    """Production data for specific commodity in a garden"""
    __tablename__ = 'data_pangan'
    id = db.Column(db.Integer, primary_key=True)
    kebun_id = db.Column(db.Integer, db.ForeignKey('kebun.id', ondelete='CASCADE'))
    komoditas_id = db.Column(db.Integer, db.ForeignKey('komoditas.id', ondelete='SET NULL'), nullable=True)
    kebun_komoditas_id = db.Column(db.Integer, db.ForeignKey('kebun_komoditas.id'), nullable=True)  # Tambahan
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    # Production data
    jml_bibit = db.Column(db.Integer, nullable=False)
    tanggal_bibit = db.Column(db.Date, nullable=False)
    jml_panen = db.Column(db.Integer, nullable=True, default=0)
    tanggal_panen = db.Column(db.Date, nullable=True)
    estimasi_panen = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Penanaman')
    is_deleted = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now())
    
    # Relationships
    kebun = db.relationship('Kebun', back_populates='data_pangan')
    komoditas_info = db.relationship('Komoditas', back_populates='data_pangan')
    kebun_komoditas = db.relationship('KebunKomoditas')  # Tambahan
    user = db.relationship('User')

# User-Kebun association table
user_kebun = db.Table('user_kebun',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE')),
    db.Column('kebun_id', db.Integer, db.ForeignKey('kebun.id', ondelete='CASCADE'))
)

# Keep existing User model and add this relationship
User.kebun = db.relationship('Kebun', secondary='user_kebun', back_populates='users')

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
    is_replied = db.Column(db.Boolean, default=False)

    creator = db.relationship('User', foreign_keys=[created_by], backref='questions')
    replier = db.relationship('User', foreign_keys=[replied_by], backref='answers')

    def __repr__(self):
        return f"Forum(ID: {self.id}, Question: {self.question[:20]}, Answer: {self.answer[:20]}, Created By: {self.created_by}, Replied By: {self.replied_by})"

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