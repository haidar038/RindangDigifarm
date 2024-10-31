import logging, jwt

from flask_socketio import emit
from flask_mail import Message
from flask_login import current_user
from flask import current_app, url_for, render_template
from itsdangerous import URLSafeTimedSerializer
from datetime import timedelta, datetime

from App import db, mail

def generate_confirmation_token(email, expiration=3600):
    """Generate JWT token for email confirmation"""
    try:
        payload = {
            'email': email,
            'exp': datetime.utcnow() + timedelta(seconds=expiration)
        }
        return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    except Exception as e:
        current_app.logger.error(f"Error generating confirmation token: {str(e)}")
        return None

def confirm_token(token, expiration=3600):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['email']
    except jwt.ExpiredSignatureError:
        current_app.logger.error("Token has expired")
        return None
    except jwt.InvalidTokenError as e:
        current_app.logger.error(f"Invalid token: {str(e)}")
        return None
    except Exception as e:
        current_app.logger.error(f"Error confirming token: {str(e)}")
        return None

def generate_forgot_password_token(email, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt=current_app.config['SECURITY_PASSWORD_SALT'])

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

# def confirm_token(token, expiration=3600):
#     serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
#     try:
#         email = serializer.loads(
#             token,
#             salt=current_app.config['SECURITY_PASSWORD_SALT'],
#             max_age=expiration
#         )
#         return email
#     except Exception as e:
#         current_app.logger.error(f"Error confirming token: {str(e)}")
#         return False

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
    # return []  # Return an empty list if not logged in

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