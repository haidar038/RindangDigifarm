import string, random, os, secrets

from flask import Blueprint, render_template, redirect, url_for, flash, current_app, request, jsonify, send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Message
from sqlalchemy import desc, func, text
from textwrap import shorten
from functools import wraps
from datetime import datetime
from flask_ckeditor.utils import cleanify
from io import BytesIO
from functools import wraps
# Reportlabs imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from App import db, mail
from App.models import UpgradeRequest, User, PetaniProfile, AhliProfile, Artikel, Role, Komoditas, DataPangan, Kebun

admin = Blueprint('admin', __name__)

PER_PAGE = 10
REPORT_ALLOWED_EXTENSIONS = {'xlsx'}
PICTURE_ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

from datetime import datetime, timedelta
import random
import json


def is_allowed_file(filename, file_type='picture'):
    """
    Check if a file has an allowed extension.

    Args:
        filename: The filename to check
        file_type: The type of file ('picture' or 'report')

    Returns:
        Boolean indicating if the file is allowed
    """
    if not filename or '.' not in filename:
        return False

    extension = filename.rsplit('.', 1)[1].lower()

    if file_type == 'picture':
        return extension in PICTURE_ALLOWED_EXTENSIONS
    elif file_type == 'report':
        return extension in REPORT_ALLOWED_EXTENSIONS

    return False

def generate_unique_id(prefix="", string_length=2, number_length=4):
    """
    Generates a unique ID in the format PREFIX_AB1234.

    Args:
        prefix: The static identifier prefix (default: "").
        string_length: The length of the random string part (default: 2).
        number_length: The length of the random number part (default: 4).

    Returns:
        A unique ID string.
    """
    random_string = ''.join(random.choices(string.ascii_uppercase, k=string_length))
    random_number = ''.join(random.choices(string.digits, k=number_length))
    unique_id = f"{prefix}{random_string}{random_number}"
    return unique_id

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_confirmed:
                flash('Anda harus login dan konfirmasi email terlebih dahulu!', 'warning')
                return redirect(url_for('public.index'))

            # Check if user has any of the required roles
            if not any(current_user.has_role(role) for role in roles):
                flash('Anda tidak memiliki izin untuk mengakses halaman ini!', 'warning')
                return redirect(url_for('public.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def view_only_access(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        allowed_views = ['index', 'productions_management']
        if current_user.has_role('view_only') and f.__name__ not in allowed_views:
            flash('Anda hanya memiliki akses view.', 'warning')
            return redirect(url_for('admin.index'))

        return f(*args, **kwargs)
    return decorated_function

@admin.route('/admin')
@login_required
@roles_required('admin', 'view_only')
@view_only_access
def index():
    # Get user statistics
    total_users = User.query.filter(User.username != 'admin').count()
    total_petani = db.session.query(func.count(User.id)).join(User.roles).filter(Role.name == 'petani').scalar() or 0
    total_ahli = db.session.query(func.count(User.id)).join(User.roles).filter(Role.name == 'ahli').scalar() or 0

    # Get article statistics
    total_articles = Artikel.query.count()
    published_articles = Artikel.query.filter(Artikel.is_approved == True).count()
    draft_articles = Artikel.query.filter(Artikel.is_drafted == True).count()

    # Get production statistics
    total_production = db.session.query(func.sum(DataPangan.jml_panen)).filter(
        DataPangan.is_deleted == False,
        DataPangan.jml_panen.isnot(None)
    ).scalar() or 0

    total_gardens = Kebun.query.filter_by(is_deleted=False).count()

    # Get recent activities
    recent_users = User.query.filter(User.username != 'admin').order_by(User.created_at.desc()).limit(5).all()
    recent_articles = Artikel.query.order_by(Artikel.created_at.desc()).limit(5).all()
    pending_upgrade_requests = UpgradeRequest.query.filter_by(status='pending').count()

    return render_template('admin/index.html',
                            total_users=total_users,
                            total_petani=total_petani,
                            total_ahli=total_ahli,
                            total_articles=total_articles,
                            published_articles=published_articles,
                            draft_articles=draft_articles,
                            total_production=total_production,
                            total_gardens=total_gardens,
                            recent_users=recent_users,
                            recent_articles=recent_articles,
                            pending_upgrade_requests=pending_upgrade_requests)

@admin.route('/admin/users-management')
@login_required
@roles_required('admin')
def users_management():
    # halaman default = 1
    page = request.args.get('page', 1, type=int)
    pagination = User.query \
                        .filter(User.username != 'admin') \
                        .order_by(User.id) \
                        .paginate(page=page, per_page=PER_PAGE, error_out=False)

    users = pagination.items
    user_req = UpgradeRequest.query.all()

    return render_template(
        'admin/users_management.html',
        users=users,
        user_req=user_req,
        pagination=pagination
    )

@admin.route('/admin/users-management/_table')
@login_required
@roles_required('admin')
def users_management_table():
    # route ini hanya render <tbody> untuk AJAX
    page = request.args.get('page', 1, type=int)
    pagination = User.query \
                        .filter(User.username != 'admin') \
                        .order_by(User.id) \
                        .paginate(page=page, per_page=PER_PAGE, error_out=False)
    users = pagination.items
    user_req = UpgradeRequest.query.all()
    return render_template(
        'admin/_users_table.html',
        users=users,
        user_req=user_req
    )

@admin.route('/admin/users-management/new', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def add_user():
    users = User.query.filter(User.username!='admin').all()
    roles = Role.query.all()

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role_name = request.form['role']

        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username sudah ada', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email sudah ada', 'danger')
        else:
            # Get the role object
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                flash('Role tidak ditemukan', 'danger')
                return redirect(url_for('admin.add_user'))

            # Create new user
            user = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
                is_confirmed=True
            )
            # Append the role object
            user.roles.append(role)

            db.session.add(user)
            db.session.commit()
            flash('User berhasil ditambahkan', 'success')
            return redirect(url_for('admin.users_management'))

    return render_template('admin/User/add_user.html', users=users, roles=roles)

# In admin_routes.py
@admin.route('/admin/users-management/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    roles = Role.query.all()
    selected_roles = [role.name for role in user.roles]

    if request.method == 'POST':
        try:
            user.username = request.form['username']
            user.email = request.form['email']

            # Handle role updates
            selected_roles = request.form.getlist('roles')
            user.roles.clear()
            for role_name in selected_roles:
                role = Role.query.filter_by(name=role_name).first()
                if role:
                    user.roles.append(role)

            db.session.commit()
            flash('User berhasil diupdate', 'success')
            return redirect(url_for('admin.users_management'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating user: {str(e)}")
            flash('Gagal mengupdate user', 'danger')
            return redirect(url_for('admin.users_management'))

    return render_template('admin/User/edit_user.html',
                            user=user,
                            roles=roles,
                            selected_roles=selected_roles)

@admin.route('/admin/users-management/delete/<int:user_id>', methods=['POST'])
@login_required
@roles_required('admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    try:
        if user.username != 'admin':
            # Soft delete
            user.is_deleted = True
            user.deleted_at = datetime.now()
            db.session.commit()
            flash('User berhasil dihapus', 'success')
        else:
            flash('Admin user tidak dapat dihapus', 'danger')

    except Exception as e:
        db.session.rollback()
        flash('Gagal menghapus user', 'danger')

    return redirect(url_for('admin.users_management'))

@admin.route('/generate-username', methods=['POST'])
def generate_username():
    name = request.json.get('name', '')
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    # Convert to lowercase and replace spaces with dots
    base_username = name.lower().replace(' ', '.')

    # Remove special characters
    base_username = ''.join(e for e in base_username if e.isalnum() or e == '.')

    # Check if username exists
    counter = 0
    username = base_username
    while User.query.filter_by(username=username).first():
        counter += 1
        username = f"{base_username}{counter}"

    return jsonify({'username': username})



@admin.route('/admin/settings')
@login_required
@roles_required('admin')
def settings():
    return render_template('admin/settings.html')

@admin.route('/admin/reports')
@login_required
@roles_required('admin', 'view_only')
@view_only_access
def reports_dashboard():
    # Get user statistics
    total_users = User.query.filter(User.username != 'admin').count()
    user_growth = random.randint(5, 15)  # Simulated growth percentage

    # Get production statistics
    total_production = db.session.query(func.sum(DataPangan.jml_panen)).filter(
        DataPangan.is_deleted == False,
        DataPangan.jml_panen.isnot(None)
    ).scalar() or 0
    production_growth = random.randint(3, 20)  # Simulated growth percentage

    # Get sales statistics (simulated for now)
    total_sales = random.randint(5000000, 15000000)
    sales_growth = random.randint(5, 25)

    # Get transaction statistics (simulated for now)
    successful_transactions = random.randint(80, 150)
    total_transactions = random.randint(successful_transactions, successful_transactions + 50)
    transaction_success_rate = int((successful_transactions / total_transactions) * 100)

    # Get recent users
    recent_users = User.query.filter(User.username != 'admin').order_by(User.created_at.desc()).limit(10).all()

    # Get recent productions
    recent_productions = db.session.query(DataPangan, User, Komoditas).join(
        User, DataPangan.user_id == User.id
    ).join(
        Komoditas, DataPangan.komoditas_id == Komoditas.id
    ).filter(
        DataPangan.is_deleted == False
    ).order_by(DataPangan.created_at.desc()).limit(10).all()

    # Process production data for template
    processed_productions = []
    for data_pangan, user, komoditas in recent_productions:
        data_pangan.user = user
        data_pangan.komoditas = komoditas
        processed_productions.append(data_pangan)

    # Generate sample data for charts
    # For line chart - last 7 days
    today = datetime.now()
    chart_labels = [(today - timedelta(days=i)).strftime('%d/%m') for i in range(7, 0, -1)]

    user_data = [random.randint(1, 10) for _ in range(7)]
    production_data = [random.randint(10, 100) for _ in range(7)]
    sales_data = [random.randint(100000, 1000000) for _ in range(7)]

    # For pie chart - commodity distribution
    commodity_query = db.session.query(
        Komoditas.nama,
        func.sum(DataPangan.jml_panen)
    ).join(
        DataPangan, Komoditas.id == DataPangan.komoditas_id
    ).filter(
        DataPangan.is_deleted == False
    ).group_by(Komoditas.nama).all()

    commodity_labels = [item[0] for item in commodity_query] or ['Padi', 'Jagung', 'Kedelai', 'Cabai', 'Bawang']
    commodity_data = [item[1] or random.randint(50, 200) for item in commodity_query] or [random.randint(50, 200) for _ in range(5)]

    # Simulated transaction data
    recent_transactions = []
    for i in range(10):
        transaction = {
            'id': f'TRX-{random.randint(1000, 9999)}',
            'buyer': random.choice(recent_users),
            'seller': random.choice(recent_users),
            'komoditas': {
                'nama': random.choice(commodity_labels)
            },
            'quantity': random.randint(5, 50),
            'total_price': random.randint(50000, 500000),
            'created_at': datetime.now() - timedelta(days=random.randint(0, 30)),
            'status': random.choice(['completed', 'pending', 'failed'])
        }
        recent_transactions.append(transaction)

    return render_template(
        'admin/reports_dashboard.html',
        total_users=total_users,
        user_growth=user_growth,
        total_production=total_production,
        production_growth=production_growth,
        total_sales=total_sales,
        sales_growth=sales_growth,
        successful_transactions=successful_transactions,
        total_transactions=total_transactions,
        transaction_success_rate=transaction_success_rate,
        recent_users=recent_users,
        recent_productions=processed_productions,
        recent_transactions=recent_transactions,
        chart_labels=chart_labels,
        user_data=user_data,
        production_data=production_data,
        sales_data=sales_data,
        commodity_labels=commodity_labels,
        commodity_data=commodity_data
    )

@admin.route('/admin/export-report')
@login_required
@roles_required('admin')
def export_report():
    format_type = request.args.get('format', 'csv')
    report_type = request.args.get('type', 'all')

    # In a real implementation, you would generate the actual report file here
    # For now, we'll just return a message
    flash(f'Laporan {report_type} berhasil diekspor dalam format {format_type.upper()}', 'success')

    # Create a notification for this action
    create_admin_notification(
        title=f'Laporan {report_type.capitalize()} Diekspor',
        message=f'Laporan {report_type} telah diekspor dalam format {format_type.upper()}',
        notification_type='report',
        user_id=current_user.id
    )

    return redirect(url_for('admin.reports_dashboard'))

@admin.route('/admin/notifications')
@login_required
@roles_required('admin')
def notifications():
    # In a real implementation, you would fetch notifications from the database
    # For now, we'll create some sample notifications
    notifications = [
        {
            'id': 1,
            'title': 'Pengguna Baru Terdaftar',
            'message': 'Pengguna baru dengan username "johndoe" telah mendaftar.',
            'type': 'user',
            'is_read': False,
            'created_at': '1 jam yang lalu',
            'action_url': url_for('admin.users_management'),
            'action_text': 'Lihat Pengguna'
        },
        {
            'id': 2,
            'title': 'Permintaan Upgrade Role',
            'message': 'Pengguna "janedoe" meminta upgrade ke role "petani".',
            'type': 'user',
            'is_read': False,
            'created_at': '3 jam yang lalu',
            'action_url': url_for('admin.view_upgrade_requests'),
            'action_text': 'Tinjau Permintaan'
        },
        {
            'id': 3,
            'title': 'Artikel Baru Ditambahkan',
            'message': 'Artikel baru "Cara Menanam Padi yang Efektif" telah ditambahkan.',
            'type': 'article',
            'is_read': True,
            'created_at': '1 hari yang lalu',
            'action_url': url_for('admin.articles_management'),
            'action_text': 'Lihat Artikel'
        },
        {
            'id': 4,
            'title': 'Data Produksi Diperbarui',
            'message': 'Data produksi untuk petani "farmer1" telah diperbarui.',
            'type': 'production',
            'is_read': True,
            'created_at': '2 hari yang lalu',
            'action_url': url_for('admin.productions_management'),
            'action_text': 'Lihat Produksi'
        },
        {
            'id': 5,
            'title': 'Transaksi Penjualan Baru',
            'message': 'Transaksi penjualan baru senilai Rp 500.000 telah dilakukan.',
            'type': 'sales',
            'is_read': False,
            'created_at': '3 hari yang lalu',
            'action_url': '#',
            'action_text': 'Lihat Transaksi'
        }
    ]

    return render_template('admin/notifications.html', notifications=notifications)

@admin.route('/admin/mark-notification-read', methods=['POST'])
@login_required
@roles_required('admin')
def mark_notification_read():
    # In a real implementation, you would update the notification in the database
    # For now, we'll just return a success response
    return jsonify({'success': True})

@admin.route('/admin/mark-all-notifications-read', methods=['POST'])
@login_required
@roles_required('admin')
def mark_all_notifications_read():
    # In a real implementation, you would update all notifications in the database
    # For now, we'll just return a success response
    return jsonify({'success': True})

# Helper function to create admin notifications
def create_admin_notification(title, message, notification_type, user_id=None, action_url=None, action_text=None):
    # In a real implementation, you would save the notification to the database
    # For now, we'll just log it
    current_app.logger.info(f"Admin Notification: {title} - {message}")

    # You would typically return the created notification
    return {
        'id': random.randint(1000, 9999),
        'title': title,
        'message': message,
        'type': notification_type,
        'is_read': False,
        'created_at': datetime.now(),
        'user_id': user_id,
        'action_url': action_url,
        'action_text': action_text
    }

@admin.route('/admin/upgrade-requests')
@login_required
@roles_required('admin')
def view_upgrade_requests():
    # Get filter parameters
    status = request.args.get('status', 'all')
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'newest')  # newest or oldest
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)

    # Base query - join with User to get user data in a single query
    query = db.session.query(UpgradeRequest).join(User)

    # Apply status filter
    if status != 'all':
        query = query.filter(UpgradeRequest.status == status)

    # Apply search if provided
    if search:
        query = query.filter(
            User.username.ilike(f'%{search}%') |
            User.email.ilike(f'%{search}%') |
            User.nama_lengkap.ilike(f'%{search}%')
        )

    # Apply sorting
    if sort == 'oldest':
        query = query.order_by(UpgradeRequest.created_at.asc())
    else:  # newest
        query = query.order_by(UpgradeRequest.created_at.desc())

    # Get paginated results
    pagination = query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    # Get status counts for filter badges in a single query
    status_counts_query = db.session.query(
        UpgradeRequest.status,
        func.count(UpgradeRequest.id)
    ).group_by(UpgradeRequest.status).all()

    # Convert query results to dictionary
    status_counts = {
        'all': sum(count for _, count in status_counts_query),
        'pending': 0,
        'approved': 0,
        'rejected': 0
    }

    for status_value, count in status_counts_query:
        status_counts[status_value] = count

    return render_template(
        'admin/upgrade_requests.html',
        requests=pagination.items,
        pagination=pagination,
        status_counts=status_counts,
        current_status=status,
        current_sort=sort,
        search=search
    )

@admin.route('/admin/upgrade-request/<int:id>/approve', methods=['POST'])
@login_required
@roles_required('admin')
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
        petani_profile = PetaniProfile(user_id=user.id, unique_id=generate_unique_id(prefix="PR_"))
        db.session.add(petani_profile)
    elif upgrade_request.requested_role == 'ahli':
        ahli_profile = AhliProfile(user_id=user.id, unique_id=generate_unique_id(prefix="PKR_"))
        db.session.add(ahli_profile)
    else:
        flash('Tipe upgrade tidak valid.', 'danger')
        return redirect(url_for('admin.view_upgrade_requests'))

    # Update the upgrade request status
    upgrade_request.status = 'approved'
    upgrade_request.updated_at = datetime.now()
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
@roles_required('admin')
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
@roles_required('admin')
def manage_roles():
    # Get all roles
    roles = Role.query.all()

    # Create sample permissions (in a real app, these would be stored in the database)
    permissions = [
        {'id': 1, 'name': 'Lihat Dashboard'},
        {'id': 2, 'name': 'Kelola Pengguna'},
        {'id': 3, 'name': 'Kelola Artikel'},
        {'id': 4, 'name': 'Kelola Produksi'},
        {'id': 5, 'name': 'Kelola Komoditas'},
        {'id': 6, 'name': 'Kelola Penjualan'},
        {'id': 7, 'name': 'Lihat Laporan'},
        {'id': 8, 'name': 'Export Data'},
        {'id': 9, 'name': 'Kelola Role'},
        {'id': 10, 'name': 'Kelola Pengaturan'}
    ]

    # Prepare role data for JavaScript
    roles_data = []
    for role in roles:
        # Count users with this role
        user_count = db.session.query(func.count(User.id)).join(User.roles).filter(Role.id == role.id).scalar() or 0

        # Get sample users with this role (in a real app, you'd query the database)
        sample_users = db.session.query(User).join(User.roles).filter(Role.id == role.id).limit(10).all()
        users_data = []

        for user in sample_users:
            users_data.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'nama_lengkap': user.nama_lengkap,
                'profile_pic': user.profile_pic,
                'created_at': user.created_at.strftime('%d/%m/%Y'),
                'edit_url': url_for('admin.edit_user', user_id=user.id)
            })

        # Assign random permissions for demo purposes
        # In a real app, you'd store and retrieve these from the database
        role_permissions = []
        if role.name == 'admin':
            role_permissions = [p['id'] for p in permissions]  # Admin has all permissions
        elif role.name == 'petani':
            role_permissions = [1, 4, 6, 7]  # Example permissions for farmers
        elif role.name == 'ahli':
            role_permissions = [1, 3, 7]  # Example permissions for experts
        elif role.name == 'personal':
            role_permissions = [1]  # Basic permissions for personal users
        elif role.name == 'view_only':
            role_permissions = [1, 7]  # View-only permissions

        roles_data.append({
            'id': role.id,
            'name': role.name,
            'description': f'Role untuk pengguna dengan tipe {role.name}',
            'user_count': user_count,
            'permissions': role_permissions,
            'users': users_data
        })

    return render_template(
        'admin/role_management.html',
        roles=roles,
        permissions=permissions,
        roles_json=json.dumps(roles_data),
        permissions_json=json.dumps(permissions)
    )

@admin.route('/admin/komoditas')
@login_required
@roles_required('admin')
def manage_commodity():
    komoditas = Komoditas.query.filter_by(is_deleted=False).all()
    return render_template('admin/manage_commodity.html', komoditas=komoditas)

# Route untuk mnambahkan komoditas baru
@admin.route('/admin/komoditas', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def add_commodity():
    komoditas = Komoditas.query.all()
    if request.method == 'POST':
        nama = request.form['nama']
        kategori = request.form['kategori']

        if nama in [cmdt.nama for cmdt in komoditas]:
            flash('Komoditas sudah ada', 'danger')
        else:
            data = Komoditas(nama=nama, kategori=kategori)
            db.session.add(data)
            db.session.commit()
            flash('Komoditas berhasil ditambahkan', 'success')
            return redirect(request.referrer)

    return render_template('admin/manage_commodity.html', komoditas=komoditas)

# Route untuk mengupdate komoditas
@admin.route('/admin/komoditas/<int:id>', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def update_commodity(id):
    komoditas = Komoditas.query.get_or_404(id)
    if request.method == 'POST':
        komoditas.nama = request.form['nama']
        komoditas.kategori = request.form['kategori']
        db.session.commit()
        flash('Komoditas berhasil diupdate', 'success')
        return redirect(url_for('admin.manage_commodity'))

# Route untuk menghapus komoditas
@admin.route('/admin/komoditas/<int:id>/delete', methods=['POST'])
@login_required
@roles_required('admin')
def delete_commodity(id):
    komoditas = Komoditas.query.get_or_404(id)
    komoditas.is_deleted = True
    db.session.commit()
    flash('Komoditas berhasil dihapus', 'success')
    return redirect(url_for('admin.manage_commodity'))

@admin.route('/admin/add-role', methods=['POST'])
@login_required
@roles_required('admin')
def add_role():
    name = request.form.get('name')
    description = request.form.get('description')

    if not name:
        flash('Nama role harus diisi', 'danger')
        return redirect(url_for('admin.manage_roles'))

    # Check if role already exists
    existing_role = Role.query.filter_by(name=name).first()
    if existing_role:
        flash(f'Role dengan nama {name} sudah ada', 'danger')
        return redirect(url_for('admin.manage_roles'))

    # Create new role
    new_role = Role(name=name, description=description)
    db.session.add(new_role)
    db.session.commit()

    flash(f'Role {name} berhasil ditambahkan', 'success')
    return redirect(url_for('admin.manage_roles'))

@admin.route('/admin/update-role', methods=['POST'])
@login_required
@roles_required('admin')
def update_role():
    role_id = request.form.get('role_id')
    name = request.form.get('name')
    description = request.form.get('description')

    if not role_id or not name:
        flash('Data tidak lengkap', 'danger')
        return redirect(url_for('admin.manage_roles'))

    # Get role
    role = Role.query.get_or_404(role_id)

    # Update role
    role.name = name
    role.description = description
    db.session.commit()

    flash(f'Role {name} berhasil diperbarui', 'success')
    return redirect(url_for('admin.manage_roles'))

@admin.route('/admin/delete-role', methods=['POST'])
@login_required
@roles_required('admin')
def delete_role():
    role_id = request.form.get('role_id')

    if not role_id:
        flash('ID role tidak valid', 'danger')
        return redirect(url_for('admin.manage_roles'))

    # Get role
    role = Role.query.get_or_404(role_id)

    # Don't allow deleting the admin role
    if role.name == 'admin':
        flash('Role admin tidak dapat dihapus', 'danger')
        return redirect(url_for('admin.manage_roles'))

    # Remove role from all users
    users_with_role = User.query.join(User.roles).filter(Role.id == role.id).all()
    for user in users_with_role:
        user.roles.remove(role)

    # Delete the role
    db.session.delete(role)
    db.session.commit()

    flash(f'Role {role.name} berhasil dihapus', 'success')
    return redirect(url_for('admin.manage_roles'))

@admin.route('/admin/articles-management')
@login_required
@roles_required('admin')
def articles_management():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'all')
    search = request.args.get('search', '')
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)

    # Join with User model to get username in a single query
    query = db.session.query(Artikel, User).join(
        User, Artikel.created_by == User.id
    )

    # Apply status filter
    if status == 'published':
        query = query.filter(Artikel.is_approved == True)
    elif status == 'draft':
        query = query.filter(Artikel.is_drafted == True)

    # Apply search if provided
    if search:
        query = query.filter(
            Artikel.judul.ilike(f'%{search}%') |
            User.username.ilike(f'%{search}%')
        )

    # Order by most recent first
    query = query.order_by(Artikel.created_at.desc())

    # Get paginated results
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Combine article data with user data
    articles = []
    for article, user in pagination.items:
        article.created_by = user
        articles.append(article)

    # Get status counts for filter badges
    status_counts = {
        'all': db.session.query(func.count(Artikel.id)).scalar() or 0,
        'published': db.session.query(func.count(Artikel.id)).filter(Artikel.is_approved == True).scalar() or 0,
        'draft': db.session.query(func.count(Artikel.id)).filter(Artikel.is_drafted == True).scalar() or 0
    }

    return render_template(
        'admin/articles_management.html',
        articles=articles,
        pagination=pagination,
        status_counts=status_counts,
        current_status=status,
        search=search
    )



@admin.route('/admin/write-article', methods=['GET', 'POST'])
@login_required
def add_article():
    articles = Artikel.query.filter_by(created_by=current_user.id)
    upload_folder = current_app.config['UPLOAD_FOLDER']

    if request.method == 'POST':
        judul = request.form['judul']
        konten = cleanify(request.form.get('ckeditor'))
        action = request.form.get('action')

        # Initialize filename
        filename = 'default_thumbnail.png'

        # Check if the post request has the file part
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file and file.filename != '':
                if is_allowed_file(file.filename, 'picture'):
                    filename = secrets.token_hex(8) + '_' + secure_filename(file.filename)
                    file_path = os.path.join(upload_folder, filename)
                    file.save(file_path)
                else:
                    flash('Format file tidak diizinkan!', 'danger')
                    return redirect(request.url)

        # Create the article
        if action == 'posting':
            add_article = Artikel(judul=judul, content=konten, created_by=current_user.id, thumbnail=filename)
        elif action == 'save':
            add_article = Artikel(judul=judul, content=konten, created_by=current_user.id, is_drafted=True, thumbnail=filename)
        else:
            flash('Aksi tidak valid!', 'danger')
            return redirect(request.url)

        db.session.add(add_article)
        db.session.commit()
        flash('Berhasil membuat artikel', 'success')
        return redirect(url_for('admin.articles_management'))

    return render_template('admin/Article/add_article.html', articles=articles)

@admin.route('/admin/articles-management/<int:id>/edit', methods=['POST', 'GET'])
@login_required
@roles_required('admin')
def edit_article(id):
    article = Artikel.query.get_or_404(id)
    if request.method == 'POST':
        try:
            article.judul = request.form['judul']
            article.content = cleanify(request.form.get('ckeditor'))
            action = request.form.get('action')

            # Handle thumbnail if new one uploaded
            if 'thumbnail' in request.files:
                thumbnail = request.files['thumbnail']
                if thumbnail and is_allowed_file(thumbnail.filename, 'report'):
                    # Delete old thumbnail if it exists and isn't default
                    if article.thumbnail != 'default_thumbnail.png':
                        old_thumbnail = os.path.join(current_app.config['UPLOAD_FOLDER'], article.thumbnail)
                        if os.path.exists(old_thumbnail):
                            os.remove(old_thumbnail)

                    filename = secure_filename(thumbnail.filename)
                    thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    thumbnail.save(thumbnail_path)
                    article.thumbnail = filename

            article.is_drafted = (action == 'save')
            article.is_approved = (action == 'publish')

            db.session.commit()
            flash('Artikel berhasil diperbarui', 'success')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating article: {str(e)}")
            flash('Gagal memperbarui artikel', 'danger')

        return redirect(url_for('admin.articles_management'))
    return render_template('admin/Article/edit_article.html', article=article)

# Redirect old update route to edit route for backward compatibility
@admin.route('/admin/articles-management/<int:id>/update', methods=['POST', 'GET'])
@login_required
@roles_required('admin')
def update_article(id):
    if request.method == 'POST':
        return edit_article(id)
    return redirect(url_for('admin.edit_article', id=id))

@admin.route('/admin/articles-management/<int:id>/approve', methods=['POST'])
@login_required
@roles_required('admin')
def approve_article(id):
    try:
        article = Artikel.query.get_or_404(id)
        article.is_approved = True
        article.is_drafted = False
        db.session.commit()
        flash('Artikel berhasil dipublikasi', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving article: {str(e)}")
        flash('Gagal mempublikasi artikel', 'danger')
    return redirect(url_for('admin.articles_management'))

@admin.route('/admin/articles-management/<int:id>/delete', methods=['POST'])
@login_required
@roles_required('admin')
def delete_article(id):
    try:
        article = Artikel.query.get_or_404(id)

        # Delete thumbnail if not default
        if article.thumbnail != 'default_thumbnail.png':
            thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], article.thumbnail)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

        db.session.delete(article)
        db.session.commit()
        flash('Artikel berhasil dihapus', 'warning')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting article: {str(e)}")
        flash('Gagal menghapus artikel', 'danger')
    return redirect(url_for('admin.articles_management'))

@admin.route('/admin/productions-management')
@login_required
@roles_required('admin', 'view_only')
@view_only_access
def productions_management():
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)

    # Get total counts for stats
    total_farmers = db.session.query(func.count(User.id)).join(User.roles).filter(Role.name == 'petani').scalar() or 0
    total_gardens = Kebun.query.filter_by(is_deleted=False).count()
    total_harvest = db.session.query(func.sum(DataPangan.jml_panen)).filter(
        DataPangan.is_deleted == False,
        DataPangan.jml_panen.isnot(None)
    ).scalar() or 0

    # Get paginated users with their total harvest in a single query using subquery
    harvest_subquery = db.session.query(
        DataPangan.user_id,
        func.sum(DataPangan.jml_panen).label('total_harvest')
    ).filter(
        DataPangan.is_deleted == False,
        DataPangan.jml_panen.isnot(None)
    ).group_by(DataPangan.user_id).subquery()

    users_query = db.session.query(
        User,
        func.coalesce(harvest_subquery.c.total_harvest, 0).label('total_harvest')
    ).outerjoin(
        harvest_subquery,
        User.id == harvest_subquery.c.user_id
    ).join(
        User.roles
    ).filter(
        Role.name == 'petani'
    ).order_by(User.id)

    # Apply pagination
    users_paginated = users_query.paginate(page=page, per_page=per_page, error_out=False)

    # Process the results to add the total_harvest attribute to each user
    users = []
    for user, total_harvest_value in users_paginated.items:
        user.total_harvest = total_harvest_value
        users.append(user)

    return render_template(
        'admin/productions_management.html',
        users=users,
        pagination=users_paginated,
        total_farmers=total_farmers,
        total_gardens=total_gardens,
        total_harvest=total_harvest
    )

@admin.route('/api/harvest-data')
@login_required
@roles_required('admin')
def get_harvest_data():
    timeframe = request.args.get('timeframe', 'monthly')

    # Base query with conditional date grouping
    base_query = db.session.query(
        DataPangan.tanggal_panen,
        func.sum(DataPangan.jml_panen).label('total_panen'),
        Komoditas.nama.label('komoditas_nama')
    ).join(
        Komoditas,
        DataPangan.komoditas_id == Komoditas.id
    ).filter(
        DataPangan.is_deleted == False,
        DataPangan.tanggal_panen.isnot(None),
        DataPangan.jml_panen.isnot(None)
    )

    # Group by timeframe
    if timeframe == 'weekly':
        base_query = base_query.group_by(func.yearweek(DataPangan.tanggal_panen), Komoditas.nama)
    elif timeframe == 'yearly':
        base_query = base_query.group_by(func.year(DataPangan.tanggal_panen), Komoditas.nama)
    else:
        base_query = base_query.group_by(func.date_format(DataPangan.tanggal_panen, '%Y-%m'), Komoditas.nama)

    results = base_query.all()

    # Format data for chart
    datasets = {}
    labels = sorted(list(set(r[0].strftime('%Y-%m-%d') for r in results)))

    for date, amount, komoditas in results:
        if komoditas not in datasets:
            datasets[komoditas] = {label: 0 for label in labels}
        datasets[komoditas][date.strftime('%Y-%m-%d')] = float(amount)

    chart_data = {
        'labels': labels,
        'datasets': [{
            'label': komoditas,
            'data': list(data.values()),
            'borderColor': f'hsl({hash(komoditas) % 360}, 70%, 50%)',
            'fill': False
        } for komoditas, data in datasets.items()]
    }

    return jsonify(chart_data)

@admin.route('/api/user-production/<int:user_id>')
@login_required
@roles_required('admin')
def get_user_production(user_id):
    user = User.query.get_or_404(user_id)

    # Get user's harvest data
    harvests = db.session.query(
        Kebun.nama.label('garden_name'),
        Komoditas.nama.label('commodity_name'),
        DataPangan.jml_panen.label('amount'),
        DataPangan.tanggal_panen
    ).join(
        Kebun,
        DataPangan.kebun_id == Kebun.id
    ).join(
        Komoditas,
        DataPangan.komoditas_id == Komoditas.id
    ).filter(
        DataPangan.user_id == user_id,
        DataPangan.is_deleted == False,
        DataPangan.tanggal_panen.isnot(None)
    ).all()

    # Chart data grouped by commodity
    chart_data = {
        'labels': [],
        'datasets': [{
            'label': 'Hasil Panen (kg)',
            'data': [],
            'backgroundColor': []
        }]
    }

    commodity_totals = {}
    for h in harvests:
        if h.commodity_name not in commodity_totals:
            commodity_totals[h.commodity_name] = 0
        commodity_totals[h.commodity_name] += h.amount

    for commodity, total in commodity_totals.items():
        chart_data['labels'].append(commodity)
        chart_data['datasets'][0]['data'].append(total)
        chart_data['datasets'][0]['backgroundColor'].append(
            f'hsl({hash(commodity) % 360}, 70%, 50%)'
        )

    return jsonify({
        'user': {
            'nama_lengkap': user.nama_lengkap,
            'total_gardens': len(user.kebun),
            'total_harvest': sum(h.amount for h in harvests)
        },
        'harvests': [
            {
                'garden_name': h.garden_name,
                'commodity_name': h.commodity_name,
                'amount': h.amount,
                'harvest_date': h.tanggal_panen.isoformat()
            }
            for h in harvests
        ],
        'chartData': chart_data
    })

@admin.route('/api/generate-report/<int:user_id>')
@login_required
@roles_required('admin')
def generate_production_report(user_id):
    user = User.query.get_or_404(user_id)

    # Get user's production data
    harvests = db.session.query(
        Kebun.nama.label('garden_name'),
        Komoditas.nama.label('commodity_name'),
        DataPangan.jml_bibit,
        DataPangan.tanggal_bibit,
        DataPangan.jml_panen,
        DataPangan.tanggal_panen
    ).join(
        Kebun,
        DataPangan.kebun_id == Kebun.id
    ).join(
        Komoditas,
        DataPangan.komoditas_id == Komoditas.id
    ).filter(
        DataPangan.user_id == user_id,
        DataPangan.is_deleted == False
    ).all()

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    elements = []
    styles = getSampleStyleSheet()

    # Add title
    title = Paragraph(f"Laporan Produksi - {user.nama_lengkap}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 20))

    # Add table
    table_data = [['Kebun', 'Komoditas', 'Jumlah Bibit', 'Tanggal Tanam', 'Hasil Panen', 'Tanggal Panen']]
    for h in harvests:
        table_data.append([
            h.garden_name,
            h.commodity_name,
            str(h.jml_bibit),
            h.tanggal_bibit.strftime('%d/%m/%Y') if h.tanggal_bibit else '-',
            f"{h.jml_panen}kg" if h.jml_panen else '-',
            h.tanggal_panen.strftime('%d/%m/%Y') if h.tanggal_panen else '-'
        ])

    # Style the table
    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    elements.append(table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'production_report_{user.username}_{datetime.now().strftime("%Y%m%d")}.pdf'
    )

@admin.route('/admin/productions-management/user/<int:user_id>')
@login_required
@roles_required('admin')
def user_production_detail(user_id):
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)

    user = User.query.get_or_404(user_id)

    productions = DataPangan.query.filter_by(
        user_id=user_id,
        is_deleted=False
    ).order_by(DataPangan.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    total_harvest = db.session.query(func.sum(DataPangan.jml_panen)).filter(
        DataPangan.user_id == user_id,
        DataPangan.is_deleted == False,
        DataPangan.jml_panen.isnot(None)
    ).scalar() or 0

    return render_template(
        'admin/user_production_detail.html',
        user=user,
        productions=productions.items,
        pagination=productions,
        total_harvest=total_harvest
    )

@admin.route('/api/generate-detailed-report/<int:user_id>')
@login_required
@roles_required('admin')
def generate_detailed_report(user_id):
    user = User.query.get_or_404(user_id)
    productions = DataPangan.query.filter_by(
        user_id=user_id,
        is_deleted=False
    ).order_by(DataPangan.tanggal_bibit.desc()).all()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    elements = []
    styles = getSampleStyleSheet()

    # Title
    title = Paragraph(f"Laporan Detail Produksi - {user.nama_lengkap}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 20))

    # Summary
    total_harvest = sum(p.jml_panen or 0 for p in productions)
    summary_data = [
        ['Total Kebun', str(len(user.kebun))],
        ['Total Hasil Panen', f"{total_harvest}kg"],
        ['Periode', f"{min(p.tanggal_bibit for p in productions).strftime('%d/%m/%Y')} - {max(p.tanggal_bibit for p in productions).strftime('%d/%m/%Y')}"]
    ]

    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey)
    ]))

    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Production details
    production_data = [['Kebun', 'Komoditas', 'Jumlah Bibit', 'Tanggal Tanam', 'Status', 'Hasil Panen', 'Tanggal Panen']]
    for p in productions:
        production_data.append([
            p.kebun.nama,
            p.komoditas_info.nama,
            str(p.jml_bibit),
            p.tanggal_bibit.strftime('%d/%m/%Y'),
            p.status,
            f"{p.jml_panen}kg" if p.jml_panen else '-',
            p.tanggal_panen.strftime('%d/%m/%Y') if p.tanggal_panen else '-'
        ])

    production_table = Table(production_data)
    production_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))

    elements.append(production_table)

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'detailed_production_report_{user.username}_{datetime.now().strftime("%Y%m%d")}.pdf'
    )