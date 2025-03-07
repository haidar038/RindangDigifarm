import smtplib, logging, jwt, os, logging, re, string

from flask import Blueprint, render_template, redirect, url_for, session, flash, request, current_app
from flask_recaptcha import ReCaptcha
from flask_mail import Message
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

from App import login_manager, db, mail, limiter
from App.utils import confirm_token, generate_confirmation_token, send_password_reset_email, send_otp_email
from App.models import User, Role
from App.forms.auth_forms import LoginForm, RegistrationForm, ForgotPasswordForm, OTPVerificationForm, ResetPasswordForm

import random, string

auth = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)
recaptcha = ReCaptcha()

def personal_unique_id(prefix="PRSNL_", string_length=2, number_length=4):
    """
    Generates a unique ID in the format RU_AB1234.

    Args:
        prefix: The static identifier prefix (default: "RU").
        string_length: The length of the random string part (default: 2).
        number_length: The length of the random number part (default: 4).

    Returns:
        A unique ID string.
    """
    random_string = ''.join(random.choices(string.ascii_uppercase, k=string_length))
    random_number = ''.join(random.choices(string.digits, k=number_length))
    unique_id = f"{prefix}{random_string}{random_number}"
    return unique_id

def validate_registration(username, email):
    suspicious_patterns = [
        r'[0-9]{5,}',         # Changed from 4+ to 5+ consecutive digits
        r'[a-zA-Z0-9]{20,}',  # Very long alphanumeric sequence
        r'[^a-zA-Z0-9_\-\.]'  # Characters other than alphanumeric, underscore, hyphen, dot
    ]
    return not any(re.search(pattern, username) for pattern in suspicious_patterns)

def log_suspicious_activity(ip, username, email):
    logger = logging.getLogger('suspicious_activity')
    logger.warning(
        f"Suspicious registration attempt - IP: {ip}, Username: {username}, Email: {email}"
    )

@auth.route('/auth/register', methods=['GET', 'POST'])
@limiter.limit("10/hour", error_message="Terlalu banyak upaya pendaftaran. Silakan coba lagi nanti")
def register():
    if current_user.is_authenticated:
        flash('Anda sudah login.', category='info')
        return redirect_based_on_role(current_user)

    form = RegistrationForm()

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form.get('confirm_password')
        username = generate_username(email)

        if not validate_registration(username, email):
            log_suspicious_activity(request.remote_addr, username, email)
            flash('Invalid registration attempt', 'danger')
            return redirect(url_for('auth.register'))
            
        if not recaptcha.verify():
            flash('Please complete the CAPTCHA', 'danger')
            return redirect(url_for('auth.register'))

        if len(password) < 8:
            flash('Kata sandi harus berisi 8 karakter atau lebih', category='danger')
            return redirect(url_for('auth.register'))
        elif confirm_password != password:
            flash('Kata sandi tidak cocok.', category='danger')
            return redirect(url_for('auth.register'))
        elif User.query.filter_by(email=email).first():
            flash('Email sudah digunakan, silakan buat yang lain.', category='danger')
            return redirect(url_for('auth.register'))

        try:
            user = User(email=email, username=username, password=generate_password_hash(password))
            personal_role = Role.query.filter_by(name='personal').first()
            if personal_role:
                user.roles.append(personal_role)
            else:
                # Handle the case where the role doesn't exist
                # You can create it or raise an error
                pass 

            db.session.add(user)
            db.session.commit()

            try:
                send_confirmation_email(email)
                flash('Akun berhasil dibuat! Silahkan cek email Anda untuk verifikasi.', category='success')
                return redirect(url_for('auth.login'))
            except Exception as email_error:
                current_app.logger.error(f"Gagal mengirim email konfirmasi: {str(email_error)}")
                flash('Akun berhasil dibuat, tetapi gagal mengirim email konfirmasi. Silakan hubungi admin.', 'warning')
                return redirect(request.referrer)
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during registration: {str(e)}")
            flash('Terjadi kesalahan saat membuat akun. Silakan coba lagi.', category='danger')
            return redirect(url_for('auth.register'))

    return render_template('auth/register.html', form=form)

def generate_username(email):
    """Generate a username from the email address."""
    username_base = email.split('@')[0]
    random_digits = ''.join(random.choice(string.digits) for _ in range(4))
    return f"{username_base}{random_digits}"

def send_confirmation_email(user_email):
    try:
        token = generate_confirmation_token(user_email)

        if request:
            base_url = request.host_url.rstrip('/')
        else:
            # Fallback to a config value if outside request context
            base_url = current_app.config.get('BASE_URL', 'http://localhost:8082')

        confirm_url = f"{base_url}{url_for('auth.confirm_email', token=token)}"
        
        html = render_template('auth/activate_email.html', confirm_url=confirm_url)
        subject = "Silakan konfirmasi email anda"
        msg = Message(subject, recipients=[user_email], html=html)

        current_app.logger.debug(f"Attempting to send email to {user_email}")
        current_app.logger.debug(f"Confirmation URL: {confirm_url}")
        
        with mail.connect() as conn:
            conn.send(msg)
        current_app.logger.info(f"Email sent successfully to {user_email}")
    except smtplib.SMTPAuthenticationError:
        current_app.logger.error("SMTP Authentication Error. Please check your username and password.")
        raise
    except smtplib.SMTPException as e:
        current_app.logger.error(f"SMTP error occurred: {str(e)}")
        raise
    except Exception as e:
        current_app.logger.error(f"Failed to send email: {str(e)}")
        current_app.logger.exception("Email sending error")
        raise

@auth.route('/auth/confirm/<token>')
def confirm_email(token):
    logger.info(f"Email confirmation attempt with token: {token[:10]}...")
    try:
        email = confirm_token(token)
    except:
        flash('Link konfirmasi tidak valid atau telah kedaluwarsa.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first_or_404()
    if user.is_confirmed:
        flash('Akun sudah dikonfirmasi. Silakan login.', 'success')
    else:
        user.is_confirmed = True
        user.confirmed_on = datetime.now()
        db.session.add(user)
        db.session.commit()

    return redirect(url_for('auth.login'))

@auth.route('/auth/reset-password', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            send_password_reset_email(user)
            flash('Email instruksi reset password telah dikirim.', category='info')
            return redirect(url_for('auth.login'))
        else:
            flash('Email tidak ditemukan.', category='danger')
            
    return render_template('auth/reset_password_request.html')

@auth.route('/auth/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = ResetPasswordForm()
        
    try:
        # Decode the JWT token
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(payload['user_id'])
        
        if not user:
            flash('Token tidak valid atau telah kadaluarsa.', category='danger')
            return redirect(url_for('auth.login'))
            
    except jwt.ExpiredSignatureError:
        flash('Token telah kadaluarsa.', category='danger')
        return redirect(url_for('auth.login'))
    except jwt.InvalidTokenError:
        flash('Token tidak valid.', category='danger')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Password tidak cocok.', category='danger')
            return redirect(url_for('auth.reset_password', token=token))
            
        if len(password) < 8:
            flash('Password minimal 8 karakter.', category='danger')
            return redirect(url_for('auth.reset_password', token=token))
            
        try:
            user.password = generate_password_hash(password)
            db.session.commit()
            flash('Password berhasil direset.', category='success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            current_app.logger.error(f"Error resetting password: {str(e)}")
            db.session.rollback()
            flash('Terjadi kesalahan saat mereset password.', category='danger')
            return redirect(url_for('auth.reset_password', token=token))
        
    return render_template('auth/reset_password.html', form=form)

@auth.route('/auth/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            try:
                # Generate and set new OTP
                user.set_otp()
                
                # Send OTP email
                send_otp_email(user.email, user.otp)
                
                # Store email in session for verification
                session['reset_email'] = user.email
                
                flash('Kode OTP telah dikirim ke email Anda.', 'success')
                return redirect(url_for('auth.verify_otp'))
            except Exception as e:
                current_app.logger.error(f"Error sending OTP: {str(e)}")
                flash('Gagal mengirim OTP. Silakan coba lagi.', 'danger')
        else:
            flash('Email tidak ditemukan.', 'danger')
    
    return render_template('auth/forgot_password.html', form=form)

@auth.route('/auth/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'reset_email' not in session:
        return redirect(url_for('auth.forgot_password'))
        
    form = OTPVerificationForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=session['reset_email']).first()
        if user and user.verify_otp(form.otp.data):
            try:
                # Generate JWT token with proper structure
                token = jwt.encode(
                    {
                        'user_id': user.id,
                        'email': user.email,
                        'exp': datetime.now() + timedelta(minutes=30)
                    },
                    current_app.config['SECRET_KEY'],
                    algorithm='HS256'
                )
                return redirect(url_for('auth.reset_password', token=token))
            except Exception as e:
                current_app.logger.error(f"Error generating reset token: {str(e)}")
                flash('Error generating reset token. Please try again.', 'danger')
        else:
            flash('OTP tidak valid atau telah kadaluarsa.', 'danger')
    
    return render_template('auth/verify_otp.html', form=form)

def send_forgot_password_token(user_email):
    try:
        token = generate_confirmation_token(user_email)

        if request:
            base_url = request.host_url.rstrip('/')
        else:
            # Fallback to a config value if outside request context
            base_url = current_app.config.get('BASE_URL', 'http://localhost:8082')

        confirm_url = f"{base_url}{url_for('auth.confirm_email', token=token)}"
        
        html = render_template('auth/activate_email.html', confirm_url=confirm_url)
        subject = "Kode OTP Lupa Kata Sandi"
        msg = Message(subject, recipients=[user_email], html=html)

        current_app.logger.debug(f"Attempting to send email to {user_email}")
        current_app.logger.debug(f"Confirmation URL: {confirm_url}")
        
        with mail.connect() as conn:
            conn.send(msg)
        current_app.logger.info(f"Email sent successfully to {user_email}")
    except smtplib.SMTPAuthenticationError:
        current_app.logger.error("SMTP Authentication Error. Please check your username and password.")
        raise
    except smtplib.SMTPException as e:
        current_app.logger.error(f"SMTP error occurred: {str(e)}")
        raise
    except Exception as e:
        current_app.logger.error(f"Failed to send email: {str(e)}")
        current_app.logger.exception("Email sending error")
        raise

@auth.route('/auth/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect_based_on_role(current_user)
    
    form = LoginForm()
        
    if request.method == 'POST':
        login_identifier = request.form['email']
        password = request.form['password']
        remember = True if request.form.get('remember') else False
        
        # Allow login with either email or username
        user = User.query.filter((User.email == login_identifier) | (User.username == login_identifier)).first()
        
        if not user or not check_password_hash(user.password, password):
            flash('Email/Username atau password salah.', category='danger')
            return redirect(url_for('auth.login'))
            
        if not user.is_confirmed:
            flash('Silakan konfirmasi email Anda terlebih dahulu.', category='warning')
            return redirect(url_for('auth.login'))
        
        # Set session duration based on remember me
        if remember:
            # Set permanent session with 30 days duration
            session.permanent = True
            login_user(user, remember=True, duration=timedelta(days=30))
        else:
            # Set permanent session with 1 day duration
            session.permanent = True
            login_user(user, remember=False, duration=timedelta(days=1))
        
        return redirect_based_on_role(user)
            
    return render_template('auth/login.html', form=form)

def redirect_based_on_role(user):
    """Helper function to handle role-based redirects"""
    if user.roles[0].name == 'admin':
        return redirect(url_for('admin.index'))
    elif user.roles[0].name == 'petani':
        return redirect(url_for('farmer.index'))
    elif user.roles[0].name == 'ahli':
        return redirect(url_for('expert.index'))
    elif user.roles[0].name == 'personal':
        return redirect(url_for('personal.index'))
    else:
        return redirect(url_for('public.index'))

@auth.before_app_request
def check_session_expiration():
    if current_user.is_authenticated:
        # Get the last activity timestamp
        last_activity = session.get('last_activity')
        now = datetime.now()
        
        if last_activity:
            last_activity = datetime.fromisoformat(last_activity)
            # Calculate expiration based on remember cookie
            remember_cookie = request.cookies.get('remember_token')
            expiration = last_activity + (
                timedelta(days=30) if remember_cookie 
                else timedelta(days=1)
            )
            
            if now > expiration:
                logout_user()
                flash('Sesi Anda telah berakhir. Silakan login kembali.', 'info')
                return redirect(url_for('auth.login'))
        
        # Update last activity
        session['last_activity'] = now.isoformat()

@auth.route('/auth/logout')
@login_required
def logout():
    logout_user()
    flash('Berhasil logout.', category='warning')
    return redirect(url_for('auth.login'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Decorator untuk mengecek role
def role_required(*roles):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if current_user.roles not in roles:
                flash('Anda tidak memiliki akses ke halaman ini.', category='danger')
                return redirect(url_for('dashboard.index'))
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper