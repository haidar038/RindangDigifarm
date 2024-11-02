import string, random

from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request
from flask_login import login_required, current_user
from flask_mail import Message
from textwrap import shorten
from functools import wraps
from datetime import datetime

from App import db, mail
from App.models import UpgradeRequest, User, PetaniProfile, AhliProfile, Artikel, Role

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

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.roles != role or not current_user.is_confirmed:
                flash(f'Anda tidak memiliki izin untuk mengakses halaman ini!', 'warning')
                return redirect(url_for('public.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@admin.route('/admin')
@login_required
@role_required('admin')
def index():
    users = User.query.filter(User.username!='admin').all()
    articles = Artikel.query.all()
    return render_template('admin/index.html', users=users, articles=articles)

@admin.route('/admin/users-management')
@login_required
@role_required('admin')
def users_management():
    users = User.query.filter(User.username!='admin').all()
    for user in users:  # Preprocess user.roles before going to template:
        user.role_names = ', '.join([role.name for role in user.roles])
    user_req = UpgradeRequest.query.all()
    
    return render_template('admin/users_management.html', users=users, user_req=user_req)

@admin.route('/admin/articles-management')
@login_required
@role_required('admin')
def articles_management():
    
    return render_template('admin/articles_management.html')

@admin.route('/admin/productions-management')
@login_required
@role_required('admin')
def productions_management():
    
    return render_template('admin/productions_management.html')

@admin.route('/admin/settings')
@login_required
@role_required('admin')
def settings():
    
    return render_template('admin/settings.html')

@admin.route('/admin/upgrade-requests')
@login_required
@role_required('admin')
def view_upgrade_requests():

    requests = UpgradeRequest.query.filter_by(status='pending').all()
    return render_template('admin/upgrade_requests.html', requests=requests, shorten=shorten)

@admin.route('/admin/upgrade-request/<int:id>/approve', methods=['POST'])
@login_required
@role_required('admin')
def approve_upgrade_request(id):

    upgrade_request = UpgradeRequest.query.get_or_404(id)
    if upgrade_request.status != 'pending':
        flash('Permintaan ini sudah diproses.', 'warning')
        return redirect(url_for('admin.view_upgrade_requests'))
    
    user = upgrade_request.user
    # Add the new role to the user
    new_role = Role.query.filter_by(name=upgrade_request.requested_role).first()
    if not new_role:
        flash('Role tidak ditemukan.', 'danger')
        return redirect(url_for('admin.view_upgrade_requests'))
    
    user.roles.append(new_role)
    # Create role-specific profile
    if upgrade_request.requested_role == 'petani':
        petani_profile = PetaniProfile(user_id=user.id, unique_id=petani_unique_id())
        db.session.add(petani_profile)
    elif upgrade_request.requested_role == 'ahli':
        ahli_profile = AhliProfile(user_id=user.id, unique_id=ahli_unique_id())
        db.session.add(ahli_profile)
    else:
        flash('Tipe upgrade tidak valid.', 'danger')
        return redirect(url_for('admin.view_upgrade_requests'))
    
    # Update the upgrade request status
    upgrade_request.status = 'approved'
    upgrade_request.updated_at = datetime.utcnow()
    db.session.commit()
    
    flash('Permintaan upgrade telah disetujui.', 'success')
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
@role_required('admin')
def reject_upgrade_request(id):

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

@admin.route('/admin/roles')
@login_required
@role_required('admin')
def manage_roles():
    roles = Role.query.all()
    return render_template('admin/manage_roles.html', roles=roles)

# Route untuk menambah role baru
@admin.route('/admin/roles/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def create_role():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        if not name:
            flash('Nama role harus diisi.', 'warning')
            return redirect(url_for('admin.create_role'))
        role = Role.query.filter_by(name=name).first()
        if role:
            flash('Role dengan nama tersebut sudah ada.', 'danger')
            return redirect(url_for('admin.create_role'))
        new_role = Role(name=name, description=description)
        db.session.add(new_role)
        db.session.commit()
        flash('Role baru berhasil ditambahkan.', 'success')
        return redirect(url_for('admin.manage_roles'))
    return render_template('admin/create_role.html')

# Route untuk mengedit role
@admin.route('/admin/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def edit_role(role_id):
    role = Role.query.get_or_404(role_id)
    if request.method == 'POST':
        role.name = request.form.get('name')
        role.description = request.form.get('description')
        db.session.commit()
        flash('Role berhasil diperbarui.', 'success')
        return redirect(url_for('admin.manage_roles'))
    return render_template('admin/edit_role.html', role=role)

# Route untuk menghapus role
@admin.route('/admin/roles/<int:role_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash('Role berhasil dihapus.', 'success')
    return redirect(url_for('admin.manage_roles'))