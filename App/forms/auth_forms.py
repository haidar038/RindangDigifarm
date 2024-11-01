# App/forms/auth_forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, TextAreaField, FileField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional
from App.models import User

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(message='Email wajib diisi.'),
        Email(message='Format email tidak valid.'),
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Password wajib diisi.')
    ])
    remember = BooleanField('Ingat Saya')

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(message='Email wajib diisi.'),
        Email(message='Format email tidak valid.')
    ])
    password = PasswordField('Password', validators=[
        DataRequired(message='Password wajib diisi.'),
        Length(min=8, message='Password minimal 8 karakter.')
    ])
    confirm_password = PasswordField('Konfirmasi Password', validators=[
        DataRequired(message='Konfirmasi password wajib diisi.'),
        EqualTo('password', message='Password tidak cocok.')
    ])

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email sudah terdaftar.')
        
class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(message='Email wajib diisi.'),
        Email(message='Format email tidak valid.')
    ])
        
class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[
        DataRequired(message='Password wajib diisi.'),
        Length(min=8, message='Password minimal 8 karakter.')
    ])
    confirm_password = PasswordField('Konfirmasi Password', validators=[
        DataRequired(message='Konfirmasi password wajib diisi.'),
        EqualTo('password', message='Password tidak cocok.')
    ])

class OTPVerificationForm(FlaskForm):
    otp = StringField('Kode OTP', validators=[
        DataRequired(message='Kode OTP wajib diisi.'),
        Length(min=6, max=6, message='Kode OTP harus 6 digit.')
    ])

class UpgradeRequestForm(FlaskForm):
    upgrade_type = SelectField('Jenis Upgrade', 
                        choices=[('petani', 'Petani'), ('ahli', 'Ahli')],
                        validators=[DataRequired()])
    reason = TextAreaField('Alasan Upgrade', 
                        validators=[DataRequired(), Length(min=50, max=500)])
    attachment = FileField('Dokumen Pendukung (PDF/Image)', 
                        validators=[Optional()])