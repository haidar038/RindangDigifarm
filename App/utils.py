import logging, jwt, requests, uuid

from flask_socketio import emit
from flask_mail import Message
from flask_login import current_user
from flask import current_app, url_for, render_template, flash
from babel.numbers import format_currency
from itsdangerous import URLSafeTimedSerializer
from datetime import timedelta, datetime

from App import mail

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Constants for default commodity and API configuration
PROVINCE_ID = 32  # Maluku Utara
REGENCY_ID = 1    # Ternate
DEFAULT_COMMODITY_ID = 7  # Cabai Merah Besar
DEFAULT_SUB_ID = 14
PRICE_TYPE_ID = 1
JENIS_ID = 1
PERIOD_ID = 1
API_URL = "https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1"

def generate_unique_id():
    """Generates a unique ID."""
    return uuid.uuid4().hex

def is_allowed_file(filename, allowed_extensions_set):
    """Checks if the file extension is in the allowed set."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions_set

def fetch_commodity_data(target_date: str, commodity_id: int = None) -> dict:
    """
    Ambil data harga komoditas dari API eksternal.

    Args:
        target_date (str): Tanggal target dalam format '06 Mei 25'.
        commodity_id (int, optional): ID komoditas. Default: Cabai Merah Besar.

    Returns:
        dict: { 'date': 'DD/MM/YYYY', 'name': 'Komoditas', 'price': 'IDR xx.xxx' }
    """
    # Gunakan default jika tidak disediakan
    if commodity_id is None:
        commodity_id = DEFAULT_COMMODITY_ID

    params = {
        "tanggal": target_date,
        "commodity": f"{commodity_id}_{DEFAULT_SUB_ID}",
        "priceType": PRICE_TYPE_ID,
        "isPasokan": 1,
        "jenis": JENIS_ID,
        "periode": PERIOD_ID,
        "provId": PROVINCE_ID,
        "_": int(datetime.now().timestamp() * 1000)
    }

    try:
        resp = requests.get(API_URL, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return {"date": target_date, "name": "-", "price": "-"}

        item = data[0]
        raw = item.get("Tanggal", "")
        parts = raw.split()
        if len(parts) != 3:
            raise ValueError(f"Unexpected date format: {raw}")
        day, mon_id, yy = parts

        # map Indonesian month abbreviations
        MONTHS = {
            'Jan':'01','Feb':'02','Mar':'03','Apr':'04','Mei':'05',
            'Jun':'06','Jul':'07','Agu':'08','Sep':'09','Okt':'10',
            'Nov':'11','Des':'12'
        }
        if mon_id not in MONTHS:
            raise ValueError(f"Unknown month abbreviation: {mon_id}")

        yyyy = '20' + yy
        formatted_date = f"{day}/{MONTHS[mon_id]}/{yyyy}"
        raw_price = item.get("Nilai", 0)
        formatted_price = format_currency(raw_price, "IDR", locale="id_ID", decimal_quantization=False)[:-3]

        return {"date": formatted_date,
                "name": item.get("Komoditas", "-"),
                "price": formatted_price}

    except requests.RequestException as e:
        logging.error(f"Error fetching commodity data: {e}")
    except Exception as e:
        logging.error(f"Error parsing commodity response: {e}")

    # Fallback jika error
    return {"date": target_date, "name": "-", "price": "-"}

def generate_confirmation_token(email: str, expiration: int = 3600) -> str:
    """
    Generate JWT token untuk konfirmasi email dengan penanganan error yang lebih baik
    
    Args:
        email (str): Email address
        expiration (int): Token expiration time in seconds (default: 1 hour)
    
    Returns:
        str: JWT token string
    """
    try:
        payload = {
            'email': email,
            'exp': datetime.utcnow() + timedelta(seconds=expiration),
            'iat': datetime.utcnow(),  # issued at
            'purpose': 'email_confirmation'  # untuk keamanan tambahan
        }
        
        token = jwt.encode(
            payload, 
            current_app.config['SECRET_KEY'], 
            algorithm='HS256'
        )
        
        current_app.logger.debug(f"Generated confirmation token for {email} with {expiration}s expiration")
        return token
        
    except Exception as e:
        current_app.logger.error(f"Error generating confirmation token: {str(e)}")
        raise Exception(f"Failed to generate confirmation token: {str(e)}")


def confirm_jwt_token(token: str) -> str:
    """
    Decode dan validasi JWT token untuk konfirmasi email
    
    Args:
        token (str): JWT token string
        
    Returns:
        str: Email address from token
        
    Raises:
        jwt.ExpiredSignatureError: Token expired
        jwt.InvalidTokenError: Invalid token
    """
    try:
        current_app.logger.debug(f"Attempting to decode token: {token[:20]}...")
        
        payload = jwt.decode(
            token, 
            current_app.config['SECRET_KEY'], 
            algorithms=['HS256']
        )
        
        email = payload.get('email')
        purpose = payload.get('purpose')
        
        if not email:
            current_app.logger.error("Email not found in token payload")
            raise jwt.InvalidTokenError("Email not found in token payload")
            
        if purpose != 'email_confirmation':
            current_app.logger.error(f"Invalid token purpose: {purpose}")
            raise jwt.InvalidTokenError("Invalid token purpose")
        
        current_app.logger.debug(f"Token successfully decoded for email: {email}")
        return email
        
    except jwt.ExpiredSignatureError:
        current_app.logger.error("JWT token expired")
        raise
    except jwt.InvalidTokenError as e:
        current_app.logger.error(f"Invalid JWT token: {e}")
        raise
    except Exception as e:
        current_app.logger.error(f"Unexpected error decoding token: {e}")
        raise jwt.InvalidTokenError(f"Token decode error: {str(e)}")


def generate_forgot_password_token(email: str, expiration: int = 3600) -> str:
    """
    Generate token untuk reset password menggunakan itsdangerous
    """
    try:
        serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        token = serializer.dumps(email, salt=current_app.config['SECURITY_PASSWORD_SALT'])
        current_app.logger.debug(f"Generated password reset token for {email}")
        return token
    except Exception as e:
        current_app.logger.error(f"Error generating password reset token: {str(e)}")
        raise


def confirm_forgot_password_token(token: str, expiration: int = 3600) -> str:
    """
    Decode token untuk reset password
    """
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token, 
            salt=current_app.config['SECURITY_PASSWORD_SALT'], 
            max_age=expiration
        )
        current_app.logger.debug(f"Password reset token confirmed for {email}")
        return email
    except Exception as e:
        current_app.logger.error(f"Error confirming password reset token: {e}")
        return None

def send_otp_email(email, otp):
    """
    Send OTP to user's email dengan error handling yang lebih baik
    """
    try:
        subject = "Kode OTP Reset Password"
        html = render_template('auth/otp_email.html', otp=otp)
        
        msg = Message(
            subject=subject, 
            recipients=[email], 
            html=html,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )

        current_app.logger.info(f"Sending OTP email to {email}")
        
        with mail.connect() as conn:
            conn.send(msg)
            
        current_app.logger.info(f"OTP email sent successfully to {email}")
        
    except Exception as e:
        current_app.logger.error(f"Failed to send OTP email to {email}: {str(e)}")
        raise Exception(f"Gagal mengirim OTP email: {str(e)}")

def send_password_reset_email(user):
    """
    Sends an email with a link to reset the user's password.
    """
    try:
        token = user.get_reset_password_token()
        if not token:
            current_app.logger.error("Failed to generate reset token")
            raise Exception("Failed to generate reset token")

        reset_url = url_for('auth.reset_password', token=token, _external=True)
        
        current_app.logger.info(f"Sending password reset email to {user.email}")
        current_app.logger.debug(f"Reset URL: {reset_url}")

        msg = Message(
            subject='Reset Password Rindang',
            recipients=[user.email],
            html=render_template('auth/reset_password_email_template.html',
                                reset_url=reset_url,
                                user=user),
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )

        with mail.connect() as conn:
            conn.send(msg)

        current_app.logger.info(f"Password reset email sent to {user.email}")
        
    except Exception as e:
        current_app.logger.error(f"Error sending password reset email to {user.email}: {str(e)}")
        raise Exception(f"Gagal mengirim email reset password: {str(e)}")

def validate_email_config():
    """
    Validasi konfigurasi email untuk memastikan semua setting sudah benar
    """
    required_configs = [
        'MAIL_SERVER',
        'MAIL_PORT', 
        'MAIL_USERNAME',
        'MAIL_PASSWORD',
        'MAIL_DEFAULT_SENDER'
    ]
    
    missing_configs = []
    for config in required_configs:
        if not current_app.config.get(config):
            missing_configs.append(config)
    
    if missing_configs:
        current_app.logger.error(f"Missing email configurations: {missing_configs}")
        return False, f"Missing configurations: {', '.join(missing_configs)}"
    
    # Test SMTP connection
    try:
        with mail.connect() as conn:
            current_app.logger.info("SMTP connection test successful")
        return True, "Email configuration is valid"
    except Exception as e:
        current_app.logger.error(f"SMTP connection test failed: {str(e)}")
        return False, f"SMTP connection failed: {str(e)}"

def test_email_sending(test_email: str):
    """
    Test function untuk mengirim email percobaan
    """
    try:
        subject = "Test Email - Rindang System"
        html = """
        <h2>Test Email</h2>
        <p>Ini adalah email percobaan dari sistem Rindang.</p>
        <p>Jika Anda menerima email ini, artinya konfigurasi email sudah benar.</p>
        <p>Waktu: {}</p>
        """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        msg = Message(
            subject=subject,
            recipients=[test_email],
            html=html,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )
        
        with mail.connect() as conn:
            conn.send(msg)
            
        current_app.logger.info(f"Test email sent successfully to {test_email}")
        return True, "Test email sent successfully"
        
    except Exception as e:
        current_app.logger.error(f"Failed to send test email: {str(e)}")
        return False, f"Failed to send test email: {str(e)}"