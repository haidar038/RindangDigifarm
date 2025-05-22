import smtplib, logging, jwt, string

from flask import Blueprint, render_template, redirect, url_for, session, flash, request, current_app
from flask_recaptcha import ReCaptcha
from flask_mail import Message
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

from App import login_manager, db, mail, limiter
from App.utils import confirm_jwt_token, generate_confirmation_token, send_password_reset_email, send_otp_email
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

def log_suspicious_activity(ip, username, email):
    logger = logging.getLogger('suspicious_activity')
    logger.warning(
        f"Suspicious registration attempt - IP: {ip}, Username: {username}, Email: {email}"
    )

@auth.route('/auth/register', methods=['GET', 'POST'])
# @limiter.limit("10/hour", error_message="Terlalu banyak upaya pendaftaran. Silakan coba lagi nanti")
def register():
    if current_user.is_authenticated:
        flash('Anda sudah login.', category='info')
        return redirect_based_on_role(current_user)

    form = RegistrationForm()

    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        # Username bisa di-generate setelah validasi email berhasil
        username = generate_username(email) 
        
        try:
            # Buat user baru dengan is_confirmed = False (default)
            user = User(
                email=email, 
                username=username, 
                password=generate_password_hash(password),
                is_confirmed=False
            )
            
            # Assign role personal
            personal_role = Role.query.filter_by(name='personal').first()
            if personal_role:
                user.roles.append(personal_role)
            else:
                # Buat role 'personal' jika belum ada
                current_app.logger.warning("Role 'personal' tidak ditemukan, membuat role baru")
                personal_role = Role(name='personal', description='Personal User')
                db.session.add(personal_role)
                # db.session.flush() # Opsional: flush jika ID role dibutuhkan segera sebelum commit
                user.roles.append(personal_role)

            # Simpan user ke database
            db.session.add(user)
            db.session.commit()
            
            current_app.logger.info(f"User {user.email} berhasil dibuat dengan ID: {user.id}")

            # Kirim email konfirmasi
            try:
                send_confirmation_email(user.email)
                flash('Akun berhasil dibuat! Silahkan cek email Anda untuk verifikasi.', category='success')
                current_app.logger.info(f"Email konfirmasi berhasil dikirim ke {user.email}")
                return redirect(url_for('auth.login'))
            except Exception as email_error:
                current_app.logger.error(f"Gagal mengirim email konfirmasi ke {user.email}: {str(email_error)}")
                # Jangan rollback user yang sudah dibuat, hanya beri peringatan
                flash('Akun berhasil dibuat, tetapi gagal mengirim email konfirmasi. Silakan hubungi admin untuk aktivasi manual.', 'warning')
                return redirect(url_for('auth.login'))
                
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during registration for {form.email.data}: {str(e)}")
            flash('Terjadi kesalahan saat membuat akun. Silakan coba lagi.', category='danger')
            return redirect(url_for('auth.register'))

    return render_template('auth/register.html', form=form)

def generate_username(email):
    """Generate a username from the email address."""
    username_base = email.split('@')[0]
    random_digits = ''.join(random.choice(string.digits) for _ in range(4))
    return f"{username_base}{random_digits}"

def send_confirmation_email(user_email):
    """
    Mengirim email konfirmasi dengan penanganan error yang lebih baik
    """
    try:
        # Generate token dengan waktu expire yang lebih lama (24 jam)
        token = generate_confirmation_token(user_email, expiration=86400)  # 24 jam

        # Dapatkan base URL
        if request:
            base_url = request.host_url.rstrip('/')
        else:
            base_url = current_app.config.get('BASE_URL', 'http://localhost:8082')

        confirm_url = f"{base_url}{url_for('auth.confirm_email', token=token)}"
        
        current_app.logger.debug(f"Generating confirmation email for {user_email}")
        current_app.logger.debug(f"Confirmation URL: {confirm_url}")
        current_app.logger.debug(f"Token (first 20 chars): {token[:20]}...")

        # Render template email
        html = render_template('auth/activate_email.html', confirm_url=confirm_url)
        subject = "Silakan konfirmasi email anda"
        
        # Buat message
        msg = Message(
            subject=subject, 
            recipients=[user_email], 
            html=html,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )

        current_app.logger.info(f"Attempting to send email to {user_email}")
        current_app.logger.debug(f"MAIL_SERVER: {current_app.config.get('MAIL_SERVER')}")
        current_app.logger.debug(f"MAIL_PORT: {current_app.config.get('MAIL_PORT')}")
        current_app.logger.debug(f"MAIL_USE_TLS: {current_app.config.get('MAIL_USE_TLS')}")
        current_app.logger.debug(f"MAIL_USERNAME: {current_app.config.get('MAIL_USERNAME')}")

        # Kirim email
        with mail.connect() as conn:
            conn.send(msg)
            
        current_app.logger.info(f"Email berhasil dikirim ke {user_email}")
        
    except smtplib.SMTPAuthenticationError as e:
        current_app.logger.error(f"SMTP Authentication Error: {str(e)}")
        current_app.logger.error("Periksa MAIL_USERNAME dan MAIL_PASSWORD di konfigurasi")
        raise Exception("Gagal autentikasi email server. Periksa konfigurasi email.")
        
    except smtplib.SMTPRecipientsRefused as e:
        current_app.logger.error(f"SMTP Recipients Refused: {str(e)}")
        raise Exception(f"Email {user_email} ditolak oleh server.")
        
    except smtplib.SMTPConnectError as e:
        current_app.logger.error(f"SMTP Connect Error: {str(e)}")
        raise Exception("Tidak dapat terhubung ke server email.")
        
    except smtplib.SMTPException as e:
        current_app.logger.error(f"SMTP error occurred: {str(e)}")
        raise Exception(f"Error SMTP: {str(e)}")
        
    except Exception as e:
        current_app.logger.error(f"Failed to send email to {user_email}: {str(e)}")
        current_app.logger.exception("Email sending error")
        raise Exception(f"Gagal mengirim email: {str(e)}")

@auth.route('/auth/confirm/<token>')
def confirm_email(token):
    """
    Konfirmasi email dengan logging yang lebih detail
    """
    current_app.logger.info(f"Email confirmation attempt with token: {token[:20]}...")
    
    try:
        # Decode token untuk mendapatkan email
        email = confirm_jwt_token(token)
        if not email:
            current_app.logger.error("Email not found in token")
            flash('Link konfirmasi tidak valid atau telah kedaluwarsa.', 'danger')
            return redirect(url_for('auth.login'))

        current_app.logger.info(f"Token decoded successfully for email: {email}")

        # Cari user berdasarkan email
        user = User.query.filter_by(email=email).first()
        if not user:
            current_app.logger.error(f"User not found for email: {email}")
            flash('User tidak ditemukan.', 'danger')
            return redirect(url_for('auth.login'))

        current_app.logger.info(f"User found: {user.id}, current is_confirmed status: {user.is_confirmed}")

        # Cek apakah sudah dikonfirmasi
        if user.is_confirmed:
            current_app.logger.info(f"User {email} already confirmed")
            flash('Akun sudah dikonfirmasi. Silakan login.', 'success')
        else:
            # Update status konfirmasi
            user.is_confirmed = True
            
            try:
                db.session.add(user)
                db.session.commit()
                current_app.logger.info(f"User {email} successfully confirmed and saved to database")
                flash('Akun berhasil dikonfirmasi. Silakan login.', 'success')
                
                # Verifikasi bahwa perubahan tersimpan
                updated_user = User.query.filter_by(email=email).first()
                current_app.logger.info(f"Verification - User {email} is_confirmed status after update: {updated_user.is_confirmed}")
                
            except Exception as db_error:
                db.session.rollback()
                current_app.logger.error(f"Database error while confirming user {email}: {str(db_error)}")
                flash('Terjadi kesalahan saat mengkonfirmasi akun. Silakan coba lagi.', 'danger')
                return redirect(url_for('auth.login'))

        return redirect(url_for('auth.login'))
        
    except jwt.ExpiredSignatureError:
        current_app.logger.error("Token expired")
        flash('Link konfirmasi telah kedaluwarsa. Silakan minta link baru.', 'danger')
        return redirect(url_for('auth.login'))
        
    except jwt.InvalidTokenError as e:
        current_app.logger.error(f"Invalid token: {str(e)}")
        flash('Link konfirmasi tidak valid. Silakan minta link baru.', 'danger')
        return redirect(url_for('auth.login'))
        
    except Exception as e:
        current_app.logger.error(f"Unexpected error during confirmation: {str(e)}")
        current_app.logger.exception("Confirmation error details")
        flash('Terjadi kesalahan saat mengkonfirmasi akun. Silakan coba lagi.', 'danger')
        return redirect(url_for('auth.login'))

# Route untuk resend confirmation email
@auth.route('/auth/resend-confirmation', methods=['GET', 'POST'])
def resend_confirmation():
    """
    Route untuk mengirim ulang email konfirmasi
    """
    if request.method == 'POST':
        email = request.form.get('email')
        
        if not email:
            flash('Email harus diisi.', 'danger')
            return redirect(url_for('auth.resend_confirmation'))
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('Email tidak ditemukan.', 'danger')
            return redirect(url_for('auth.resend_confirmation'))
        
        if user.is_confirmed:
            flash('Akun sudah dikonfirmasi. Silakan login.', 'info')
            return redirect(url_for('auth.login'))
        
        try:
            send_confirmation_email(email)
            flash('Email konfirmasi berhasil dikirim ulang. Silakan cek email Anda.', 'success')
            current_app.logger.info(f"Confirmation email resent to {email}")
        except Exception as e:
            current_app.logger.error(f"Failed to resend confirmation email to {email}: {str(e)}")
            flash('Gagal mengirim email konfirmasi. Silakan coba lagi nanti.', 'danger')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/resend_confirmation.html')

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
            flash('Silakan konfirmasi email Anda terlebih dahulu. <a href="{}">Kirim ulang email konfirmasi</a>'.format(url_for('auth.resend_confirmation')), category='warning')
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

        current_app.logger.info(f"User {user.email} logged in successfully")
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

@auth.route('/test-email')
def test_email():
    from App.utils import test_email_sending, validate_email_config
    
    # Validasi konfigurasi
    is_valid, message = validate_email_config()
    if not is_valid:
        return f"Email config error: {message}"
    
    # Test kirim email
    success, result = test_email_sending('haidar038@gmail.com')
    return f"Email test result: {result}"

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