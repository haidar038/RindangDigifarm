import string, random, os

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

REPORT_ALLOWED_EXTENSIONS = {'xlsx'}

def allowed_file(filename):
    return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in REPORT_ALLOWED_EXTENSIONS

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

@admin.route('/admin')
@login_required
@roles_required('admin', 'view only')
def index():
    users = User.query.filter(User.username!='admin').all()
    articles = Artikel.query.all()
    return render_template('admin/index.html', users=users, articles=articles)

@admin.route('/admin/users-management')
@login_required
@roles_required('admin')
def users_management():
    users = User.query.filter(User.username!='admin').all()
    for user in users:  # Preprocess user.roles before going to template:
        user.role_names = ', '.join([role.name for role in user.roles])
    user_req = UpgradeRequest.query.all()
    
    return render_template('admin/users_management.html', users=users, user_req=user_req)

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

            # Update roles
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
            flash('Gagal mengupdate user', 'danger')

    return render_template('admin/User/edit_user.html', user=user, roles=roles, selected_roles=selected_roles)

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

# @admin.route('/admin/productions-management')
# @login_required
# @roles_required('admin')
# def productions_management():
#     return render_template('admin/productions_management.html')

@admin.route('/admin/settings')
@login_required
@roles_required('admin')
def settings():
    return render_template('admin/settings.html')

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

    # Base query
    query = UpgradeRequest.query

    # Apply status filter
    if status != 'all':
        query = query.filter(UpgradeRequest.status == status)

    # Apply search if provided
    if search:
        query = query.join(User).filter(
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

    # Get status counts for filter badges
    status_counts = {
        'all': UpgradeRequest.query.count(),
        'pending': UpgradeRequest.query.filter_by(status='pending').count(),
        'approved': UpgradeRequest.query.filter_by(status='approved').count(),
        'rejected': UpgradeRequest.query.filter_by(status='rejected').count()
    }

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
    roles = Role.query.all()
    return render_template('admin/manage_roles.html', roles=roles)

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

        if nama in [komoditas.nama_komoditas for komoditas in komoditas]:
            flash('Komoditas sudah ada', 'danger')
        else:
            data = Komoditas(nama=nama, kategori=kategori)
            db.session.add(data)
            db.session.commit()
            flash('Komoditas berhasil ditambahkan', 'success')
            return redirect(request.referrer)
        
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

# Route untuk menambah role baru
@admin.route('/admin/roles/new', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
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
@roles_required('admin')
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
@roles_required('admin')
def delete_role(role_id):
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash('Role berhasil dihapus.', 'success')
    return redirect(url_for('admin.manage_roles'))

@admin.route('/admin/articles-management')
@login_required
@roles_required('admin')
def articles_management():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'all')
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)
    
    # Join with User model to get username
    query = db.session.query(Artikel, User).join(
        User, Artikel.created_by == User.id
    )
    
    # Apply status filter
    if status == 'published':
        query = query.filter(Artikel.is_approved == True)
    elif status == 'draft':
        query = query.filter(Artikel.is_drafted == True)
    
    query = query.order_by(Artikel.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Combine article data with user data
    articles = []
    for article, user in pagination.items:
        article.created_by = user
        articles.append(article)
    
    return render_template(
        'admin/articles_management.html',
        articles=articles,
        pagination=pagination
    )

@admin.route('/admin/articles-management/add', methods=['POST'])
@login_required
@roles_required('admin')
def add_article():
    try:
        judul = request.form['judul']
        content = cleanify(request.form.get('ckeditor'))
        action = request.form.get('action')
        
        # Handle thumbnail
        thumbnail = request.files['thumbnail']
        if thumbnail and allowed_file(thumbnail.filename):
            filename = secure_filename(thumbnail.filename)
            thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            thumbnail.save(thumbnail_path)
        else:
            filename = 'default_thumbnail.jpg'
        
        # Create article
        article = Artikel(
            judul=judul,
            content=content,
            thumbnail=filename,
            created_by=current_user.id,
            is_drafted=(action == 'save'),
            is_approved=(action == 'publish')
        )
        
        db.session.add(article)
        db.session.commit()
        flash('Artikel berhasil ditambahkan', 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding article: {str(e)}")
        flash('Gagal menambahkan artikel', 'danger')
    
    return redirect(url_for('admin.articles_management'))

@admin.route('/admin/articles-management/<int:id>/update', methods=['POST'])
@login_required
@roles_required('admin')
def update_article(id):
    try:
        article = Artikel.query.get_or_404(id)
        
        article.judul = request.form['judul']
        article.content = cleanify(request.form.get('ckeditor'))
        action = request.form.get('action')
        
        # Handle thumbnail if new one uploaded
        if 'thumbnail' in request.files:
            thumbnail = request.files['thumbnail']
            if thumbnail and allowed_file(thumbnail.filename):
                # Delete old thumbnail if it exists and isn't default
                if article.thumbnail != 'default_thumbnail.jpg':
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
        if article.thumbnail != 'default_thumbnail.jpg':
            thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], article.thumbnail)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        
        db.session.delete(article)
        db.session.commit()
        flash('Artikel berhasil dihapus', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting article: {str(e)}")
        flash('Gagal menghapus artikel', 'danger')
    return redirect(url_for('admin.articles_management'))

@admin.route('/admin/productions-management')
@login_required
@roles_required('admin')
def productions_management():
    page = request.args.get('page', 1, type=int)
    per_page = current_app.config.get('ITEMS_PER_PAGE', 10)
    
    # Get users with harvest data
    users = User.query.join(User.roles).filter(Role.name == 'petani').all()

    for user in users:
        # Calculate total harvest for each user
        user.total_harvest = db.session.query(func.sum(DataPangan.jml_panen)).filter(
            DataPangan.user_id == user.id,
            DataPangan.is_deleted == False,
            DataPangan.jml_panen.isnot(None)
        ).scalar() or 0

    # Pagination
    users_paginated = User.query.join(User.roles).filter(Role.name == 'petani').paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Overall stats
    total_farmers = len(users)
    total_gardens = Kebun.query.filter_by(is_deleted=False).count()
    total_harvest = sum(user.total_harvest for user in users)
    
    return render_template(
        'admin/productions_management.html',
        users=users_paginated.items,
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