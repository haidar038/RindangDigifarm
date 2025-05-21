import logging, jwt, requests

from flask_socketio import emit
from flask_mail import Message
from flask_login import current_user
from flask import current_app, url_for, render_template, flash
from babel.numbers import format_currency
from itsdangerous import URLSafeTimedSerializer
from datetime import timedelta, datetime

from App import mail

# Constants for default commodity and API configuration
PROVINCE_ID = 32  # Maluku Utara
REGENCY_ID = 1    # Ternate
DEFAULT_COMMODITY_ID = 7  # Cabai Merah Besar
DEFAULT_SUB_ID = 14
PRICE_TYPE_ID = 1
JENIS_ID = 1
PERIOD_ID = 1
API_URL = "https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1"


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
    payload = {'email': email, 'exp': datetime.utcnow() + timedelta(seconds=expiration)}
    return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')


def confirm_jwt_token(token: str) -> str:
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        email = payload.get('email')
        if not email:
            logging.error("Email not found in token payload")
            raise jwt.InvalidTokenError("Email not found in token payload")
        return email
    except jwt.ExpiredSignatureError:
        logging.error("JWT token expired")
        raise
    except jwt.InvalidTokenError as e:
        logging.error(f"Invalid JWT token: {e}")
        raise


def generate_forgot_password_token(email: str, expiration: int = 3600) -> str:
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=current_app.config['SECURITY_PASSWORD_SALT'])


def confirm_forgot_password_token(token: str, expiration: int = 3600) -> str:
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(token, salt=current_app.config['SECURITY_PASSWORD_SALT'], max_age=expiration)
        return email
    except Exception as e:
        logging.error(f"Error confirming password reset token: {e}")
        return None

def send_otp_email(email, otp):
    """Send OTP to user's email"""
    try:
        subject = "Kode OTP Reset Password"
        html = render_template('auth/otp_email.html', otp=otp)
        msg = Message(subject, recipients=[email], html=html)

        with mail.connect() as conn:
            conn.send(msg)
        current_app.logger.info(f"OTP email sent successfully to {email}")
    except Exception as e:
        current_app.logger.error(f"Failed to send OTP email: {str(e)}")
        raise

def send_password_reset_email(user):
    """Sends an email with a link to reset the user's password."""
    try:
        token = user.get_reset_password_token()
        if not token:
            current_app.logger.error("Failed to generate reset token")
            raise Exception("Failed to generate reset token")

        reset_url = url_for('auth.reset_password', token=token, _external=True)

        msg = Message(
            subject='Reset Password Rindang',
            recipients=[user.email],
            html=render_template('auth/reset_password_email_template.html',
                                reset_url=reset_url,
                                user=user)
        )

        with mail.connect() as conn:
            conn.send(msg)

        current_app.logger.info(f"Password reset email sent to {user.email}")
    except Exception as e:
        current_app.logger.error(f"Error sending password reset email: {str(e)}")
        raise

# def get_unread_notifications():
#     if current_user.is_authenticated:
#         return Notification.query.filter_by(recipient_id=current_user.id, is_read=False).all()
#     return []  # Return an empty list if not logged in

# def get_user_notification_room(user_id):
#     return f"user_{user_id}_notifications"

# def send_notification(recipient_id, message, sender_id=None):
#     """Sends a notification to a user and creates a database record.

#     Args:
#         recipient_id (str): ID of the recipient user.
#         message (str): The notification message.
#         sender_id (str, optional): ID of the sender user. Defaults to None.
#     """

#     room = get_user_notification_room(recipient_id)

#     notification = Notification(
#         recipient_id=recipient_id,
#         message=message,
#         sender_id=sender_id  # Optional
#     )
#     db.session.add(notification)
#     db.session.commit()

#     unread_count = len(get_unread_notifications()) # Function to get unread count

#     # Include unread count in emitted data
#     emit('new_notification', {
#         'message': message,
#         'room': room,
#         'count': unread_count
#     }, room=room, namespace='/')