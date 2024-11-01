import string, random

from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from textwrap import shorten
from datetime import datetime
from flask_mail import Message

from App import db, mail
from App.models import UpgradeRequest, User, Petani, Ahli, Artikel, Role

admin = Blueprint('admin', __name__)

def petani_unique_id(prefix="PR_", string_length=2, number_length=4):
    """
    Generates a unique ID in the format PR_AB1234.

    Args:
        prefix: The static identifier prefix (default: "PR").
        string_length: The length of the random string part (default: 2).
        number_length: The length of the random number part (default: 4).

    Returns:
        A unique ID string.
    """
    random_string = ''.join(random.choices(string.ascii_uppercase, k=string_length))
    random_number = ''.join(random.choices(string.digits, k=number_length))
    unique_id = f"{prefix}{random_string}{random_number}"
    return unique_id

def ahli_unique_id(prefix="PKR_", string_length=2, number_length=4):
    """
    Generates a unique ID in the format PKR_AB1234.

    Args:
        prefix: The static identifier prefix (default: "PKR").
        string_length: The length of the random string part (default: 2).
        number_length: The length of the random number part (default: 4).

    Returns:
        A unique ID string.
    """
    random_string = ''.join(random.choices(string.ascii_uppercase, k=string_length))
    random_number = ''.join(random.choices(string.digits, k=number_length))
    unique_id = f"{prefix}{random_string}{random_number}"
    return unique_id

@admin.route('/admin')
@login_required
def index():
    users = User.query.filter(User.type!='admin').all()
    articles = Artikel.query.all()
    return render_template('admin/index.html', users=users, articles=articles)

@admin.route('/admin/users-management')
@login_required
def users_management():
    users = User.query.filter(User.type!='admin')
    user_req = UpgradeRequest.query.all()
    
    return render_template('admin/users_management.html', users=users, user_req=user_req)

@admin.route('/admin/articles-management')
@login_required
def articles_management():
    return render_template('admin/articles_management.html')

@admin.route('/admin/productions-management')
@login_required
def productions_management():
    return render_template('admin/productions_management.html')

@admin.route('/admin/settings')
@login_required
def settings():
    return render_template('admin/settings.html')

@admin.route('/admin/upgrade-requests')
@login_required
def view_upgrade_requests():
    if current_user.type != 'admin':
        flash('Anda tidak memiliki akses ke halaman ini.', 'danger')
        return redirect(url_for('public.index'))
    
    requests = UpgradeRequest.query.filter_by(status='pending').all()
    return render_template('admin/upgrade_requests.html', requests=requests, shorten=shorten)

@admin.route('/admin/upgrade-request/<int:id>/approve', methods=['POST'])
@login_required
def approve_upgrade_request(id):
    if current_user.type != 'admin':
        flash('Anda tidak memiliki akses ke halaman ini.', 'danger')
        return redirect(url_for('public.index'))
    
    upgrade_request = UpgradeRequest.query.get_or_404(id)
    if upgrade_request.status != 'pending':
        flash('Permintaan ini sudah diproses.', 'warning')
        return redirect(url_for('admin.view_upgrade_requests'))

    user = User.query.get(upgrade_request.user_id)
    
    try:
        # Update type/role pada instance User yang sudah ada
        user.type = upgrade_request.requested_role  # Mengubah polymorphic identity
        
        if upgrade_request.requested_role == 'petani':
            # Tambahkan data spesifik Petani
            petani_data = {
                'unique_id': petani_unique_id(),
                'kebun_area': None,
                'luas_lahan': None
            }
            for key, value in petani_data.items():
                setattr(user, key, value)
                
        elif upgrade_request.requested_role == 'ahli':
            # Tambahkan data spesifik Ahli
            ahli_data = {
                'unique_id': ahli_unique_id(),
                'institusi': None,
                'bidang_keahlian': None,
                'gelar': None
            }
            for key, value in ahli_data.items():
                setattr(user, key, value)

        # Update status permintaan
        upgrade_request.status = 'approved'
        
        db.session.commit()
        flash('Permintaan upgrade akun telah disetujui.', 'success')
        
        # Opsional: Kirim notifikasi email ke pengguna
        # send_upgrade_approval_email(user.email, upgrade_request.upgrade_type.value)
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat menyetujui permintaan upgrade: {str(e)}")
        flash('Terjadi kesalahan saat menyetujui permintaan.', 'danger')
    
    return redirect(url_for('admin.view_upgrade_requests'))

def send_upgrade_approval_email(upgrade_request):
    """Mengirim email notifikasi ke admin tentang permintaan upgrade baru."""
    admin_email = current_app.config.get('ADMIN_EMAIL')
    if not admin_email:
        current_app.logger.error('Admin email tidak dikonfigurasi.')
        return
    
    subject = "Permintaan Upgrade Akun Baru"
    body = f"""
    Hai Admin,

    Pengguna dengan username '{upgrade_request.user.username}' dan email '{upgrade_request.user.email}' telah mengajukan permintaan upgrade akun ke '{upgrade_request.upgrade_type.value.title()}'.

    Alasan:
    {upgrade_request.reason}

    Silakan kunjungi dashboard admin untuk memproses permintaan ini.

    Terima kasih.
    """
    msg = Message(subject=subject, recipients=[admin_email], body=body)
    try:
        mail.send(msg)
        current_app.logger.info(f"Email notifikasi permintaan upgrade dikirim ke {admin_email}.")
    except Exception as e:
        current_app.logger.error(f"Gagal mengirim email notifikasi upgrade: {str(e)}")

@admin.route('/admin/upgrade-request/<int:id>/reject', methods=['POST'])
@login_required
def reject_upgrade_request(id):
    if current_user.type != 'admin':
        flash('Anda tidak memiliki akses ke halaman ini.', 'danger')
        return redirect(url_for('public.index'))
    
    upgrade_request = UpgradeRequest.query.get_or_404(id)
    if upgrade_request.status != 'pending':
        flash('Permintaan ini sudah diproses.', 'warning')
        return redirect(url_for('admin.view_upgrade_requests'))
    
    upgrade_request.status = 'rejected'
    
    try:
        db.session.commit()
        flash('Permintaan upgrade akun telah ditolak.', 'info')
        # Opsional: Kirim notifikasi email ke pengguna
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saat menolak permintaan upgrade: {str(e)}")
        flash('Terjadi kesalahan saat menolak permintaan.', 'danger')
    
    return redirect(url_for('admin.view_upgrade_requests'))