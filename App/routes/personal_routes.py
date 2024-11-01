import os, secrets, requests, smtplib

from flask import Blueprint, render_template, redirect, url_for,session, current_app, request, flash, jsonify
from flask_login import login_required, current_user
from flask_ckeditor.utils import cleanify
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
from flask_mail import Mail, Message
from datetime import datetime

from App import db, mail
from App.models import User, Kebun, Artikel, Forum, UpgradeRequest
from App.forms.auth_forms import UpgradeRequestForm

personal = Blueprint('personal', __name__)

PICTURE_ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def picture_allowed_file(filename):
    return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in PICTURE_ALLOWED_EXTENSIONS

@personal.route('/personal')
def index():
    users = User.query.filter_by(id=current_user.id)

    pagination_pages = 5
    page = request.args.get('page', 1, type=int)
    articles_pagination = Artikel.query.paginate(page=page, per_page=pagination_pages) #<-- MOVE THIS LINE OUT OF IF BLOCK!
    forum_pagination = Forum.query.paginate(page=page, per_page=pagination_pages) #<-- MOVE THIS LINE OUT OF IF BLOCK!

    if not articles_pagination.items: #Check if articles exist on the CURRENT page
        articles = []  # If not any article found for the page assign an empty array and handle no data condition at template
    else:
        articles = articles_pagination.items

    if not forum_pagination.items: #Check if articles exist on the CURRENT page
        forum = []  # If not any article found for the page assign an empty array and handle no data condition at template
    else:
        forum = forum_pagination.items

    return render_template('personal/index.html', users=users, articles=articles, forum=forum, min=min, max=max, articles_pagination=articles_pagination, forum_pagination=forum_pagination)

@personal.route('/rindang-ask', methods=['GET', 'POST'])
def rindang_ask():
    questions = Forum.query.filter_by(created_by=current_user.id).all()
    fetch_ahli_email = User.query.filter_by(role='ahli').all()
    ahli_emails = fetch_ahli_email

    print(ahli_emails)

    if request.method == 'POST':
        nama = request.form['nama_lengkap']
        email = request.form['email']
        question = request.form['question']

        try:
            add_question = Forum(question=question, created_by=current_user.id)
            db.session.add(add_question)
            db.session.commit()
            forum_email(user_email=email, question=question)
            flash('Pertanyaan anda telah terkirim', 'success')
            return redirect(request.referrer)
        except:
            flash('Terjadi kesalahan saat mengirimkan pertanyaan, silakan coba kembali', 'danger')
            return redirect(request.referrer)
    return render_template('personal/rindang_ask.html', questions=questions)

@personal.route('/avatar/<string:name>', methods=['GET', 'POST'])
def get_avatar(name):
    # Encoding untuk menghindari masalah karakter khusus
    encoded_name = name.encode('utf-8').decode('ascii', 'ignore')
    # Membangun URL avatar dengan aman
    avatar_url = f"https://ui-avatars.com/api/?name={encoded_name}&background=random&length=1&bold=true&rounded=true"
    return redirect(avatar_url) # Redirect ke URL avatar

def forum_email(user_email, question):
    try:
        subject = "Pertanyaan Terkirim ke RindangTalk"
        msg = Message(subject=subject, sender=('official@rindang.net'), recipients=[user_email], body=f'Anda mengirim pertanyaan ke ahli dengan dengan detail sebagai berikut: {question}')
        
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

def forum_email_to_ahli(user_email, user_name, question):
    try:
        subject = "Anda "
        msg = Message(subject=subject, sender=('official@rindang.net'), recipients=[user_email], body=f'Anda mendapatkan pertanyaan dari seorang pengguna dengan nama {user_name}, yaitu: {question}')
        
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

@personal.route('/rindangtalk/question_details/<int:id>', methods=['GET'])
@login_required
def questiondetails(id):
    data = Forum.query.get_or_404(id)
    return render_template('personal/question_details.html', data=data)

@personal.route('/rindangtalk/update_question/<int:id>', methods=['GET', 'POST'])
@login_required
def update_question(id):
    data = Forum.query.get_or_404(id)
    return render_template('personal/update_question.html', data=data)

@personal.route('/rindangtalk/delete_question/<int:id>', methods=['GET', 'POST'])
@login_required
def delete_question(id):
    question = Forum.query.get_or_404(id)
    db.session.delete(question)
    db.session.commit()
    flash('Berhasil menghapus pertanyaan!', 'warning')
    return redirect(url_for('views.personal'))

@personal.route('/personal/article-preview/<int:id>', methods=['GET'])
@login_required
def article_preview(id):
    article = Artikel.query.get_or_404(id)
    if article.is_drafted:
        flash('Artikel tidak tersedia!', 'warning')
        return redirect(request.referrer)
    created_by = User.query.filter_by(id=article.created_by).first()
    return render_template('personal/article_preview.html', article=article, created_by=created_by.nama_lengkap)

@personal.route('/personal/write-article', methods=['GET', 'POST'])
@login_required
def write_article():
    articles = Artikel.query.filter_by(created_by=current_user.id)
    upload_folder = current_app.config['UPLOAD_FOLDER']

    if request.method == 'POST':
        judul = request.form['judul']
        konten = cleanify(request.form.get('ckeditor'))
        action = request.form.get('action')

        # Initialize filename
        filename = 'default_thumbnail.jpg'

        # Check if the post request has the file part
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file and file.filename != '':
                if picture_allowed_file(file.filename):
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
        return redirect(url_for('personal.index'))

    return render_template('personal/write_article.html', articles=articles)

@personal.route('/personal/update-article/<int:id>', methods=['GET', 'POST'])
@login_required
def update_article(id):
    article = Artikel.query.filter_by(created_by=current_user.id, id=id).first()

    if request.method == 'POST':
        article.judul = request.form['judul']
        article.content = request.form.get('ckeditor')
        if request.form['action'] == 'posting':
            article.is_drafted = False
        elif request.form['action'] == 'save':
            article.is_drafted = True
        db.session.commit()
        flash('Berhasil memperbarui artikel', 'success')
        return redirect(url_for('personal.index'))
    return render_template('personal/update_article.html', article=article)

@personal.route('/personal/delete_article/<int:id>', methods=['GET', 'POST'])
@login_required
def delete_article(id):
    article = Artikel.query.filter_by(created_by=current_user.id, id=id).first()
    db.session.delete(article)
    db.session.commit()
    flash('Berhasil menghapus artikel', 'warning')
    return redirect(url_for('personal.index'))

@personal.route('/personal/profile')
@login_required
def profile():
    form = UpgradeRequestForm()
    print(current_user.roles)
    return render_template('personal/profile.html', form=form)

@personal.route('/personal/profile/update/<int:id>', methods=['GET', 'POST'])
@login_required
def updateprofil(id):
    user = User.query.get_or_404(id)
    kebun = Kebun.query.filter_by(user_id=current_user.id).first()

    form_type = request.form.get('formType')

    if request.method == 'POST':
        if form_type == 'Data User':
            # Memperbarui data user dengan data dari form
            user.nama_lengkap = request.form['nama']
            user.username = request.form['username']
            user.pekerjaan = request.form['pekerjaan']
            user.kelamin = request.form['kelamin']
            user.phone = request.form['phone']

            # Hanya update data wilayah jika ada perubahan
            user.kota = request.form['regency'] if request.form['regency'] else user.kota
            user.kec = request.form['district'] if request.form['district'] else user.kec
            user.kelurahan = request.form['village'] if request.form['village'] else user.kelurahan

            user.bio = request.form['bio']

            db.session.commit()
            flash('Profil Berhasil Diubah', category='success')
            return redirect(url_for('personal.profile')) 

        elif form_type == 'Data Kebun':
            if kebun:
                # Memperbarui data kelurahan dengan data dari form
                kebun.nama = request.form['nama_kebun']
                kebun.luas_kebun = request.form['luaskebun']
                kebun.koordinat = request.form['updateKoordinat']
            else:
                # Hanya buat kebun baru jika pengguna belum memiliki kebun
                new_kebun = Kebun(
                    user_id=user.id,
                    nama=request.form['nama_kebun'],
                    luas_kebun=request.form['luaskebun'],
                    koordinat=request.form['updateKoordinat']
                )
                db.session.add(new_kebun)

            db.session.commit()
            flash('Data Kebun Berhasil diubah!', category='success')
            return redirect(url_for('personal.profile')) 

        else:
            flash('Tipe form tidak valid!', category='danger')
            return redirect(url_for('personal.profile'))

    return render_template('dashboard/profil.html', user=user, kebun=kebun)

@personal.route('/api/proxy/<path:url>')
def proxy(url):
    try:
        response = requests.get(f'https://emsifa.github.io/api-wilayah-indonesia/api/{url}')
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        print(f"Error in proxy: {str(e)}")  # Log error
        return jsonify({"error": str(e)}), 500

@personal.route('/personal/profile/update_picture/<int:id>', methods=['POST', 'GET'])
@login_required
def update_profile_picture(id):
    upload_folder = current_app.config['UPLOAD_FOLDER']
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        if 'profile_pic' not in request.files:
            flash('Tidak ada file yang dipilih!', 'danger')
            return redirect(request.url)
        file = request.files['profile_pic']
        if file.filename == '':
            flash('Tidak ada file yang dipilih!', 'danger')
            return redirect(request.url)
        if file and picture_allowed_file(file.filename):
            filename = secrets.token_hex(8) + '_' + secure_filename(file.filename)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)

            # Hapus foto profil lama jika ada
            if user.profile_pic:
                old_file_path = os.path.join(upload_folder, user.profile_pic)
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)

            user.profile_pic = filename
            db.session.commit()
            flash('Foto profil berhasil diubah!', 'success')
        else:
            flash('File yang diizinkan hanya JPG, JPEG, dan PNG.', 'warning')
    return redirect(url_for('personal.profile'))

@personal.route('/personal/request-upgrade', methods=['POST'])
@login_required
def request_upgrade():
    form = UpgradeRequestForm()
    
    if form.validate_on_submit():
        # Cek apakah user sudah memiliki role yang diminta
        if form.upgrade_type.data in [role.name for role in current_user.roles]:
            flash(f'Anda sudah memiliki role {form.upgrade_type.data}!', 'warning')
            return redirect(url_for('personal.profile'))
            
        # Cek apakah ada permintaan yang masih pending
        pending_request = UpgradeRequest.query.filter_by(
            user_id=current_user.id,
            requested_role=form.upgrade_type.data,
            status='pending'
        ).first()
        
        if pending_request:
            flash('Anda masih memiliki permintaan upgrade yang sedang diproses!', 'warning')
            return redirect(url_for('personal.profile'))

        # Handle file upload
        attachment_filename = None
        if form.attachment.data:
            if allowed_file(form.attachment.data.filename):
                filename = secure_filename(form.attachment.data.filename)
                filename = f"upgrade_{current_user.id}_{int(datetime.now().timestamp())}_{filename}"
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'upgrade_attachments')
                os.makedirs(upload_folder, exist_ok=True)
                form.attachment.data.save(os.path.join(upload_folder, filename))
                attachment_filename = f"upgrade_attachments/{filename}"
            else:
                flash('Format file tidak diizinkan!', 'danger')
                return redirect(url_for('personal.profile'))

        try:
            upgrade_request = UpgradeRequest(
                user_id=current_user.id,
                requested_role=form.upgrade_type.data,
                reason=form.reason.data,
                attachment=attachment_filename
            )
            db.session.add(upgrade_request)
            db.session.commit()
            
            flash('Permintaan upgrade akun telah dikirim dan sedang dalam proses verifikasi.', 'success')
            return redirect(url_for('personal.profile'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error saat mengajukan upgrade request: {str(e)}")
            flash('Terjadi kesalahan saat mengirim permintaan upgrade.', 'danger')
            return redirect(url_for('personal.profile'))
            
    return redirect(url_for('personal.profile'))

def allowed_file(filename):
    """Memeriksa apakah file memiliki ekstensi yang diperbolehkan."""
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'pdf'})
    return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in allowed_extensions

def send_admin_upgrade_request_notification(upgrade_request):
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

@personal.route('/personal/pengaturan', methods=['GET', 'POST'])
def settings():
    return render_template('personal/settings.html')

@personal.route('/dashboard/pengaturan/<int:id>/update-email', methods=['GET', 'POST'])
@login_required
def updateemail(id):
    user = User.query.get_or_404(id)
    password = request.form['userPass']

    if request.method == 'POST':
        if check_password_hash(current_user.password, password):
            user.email = request.form['email']
            db.session.commit()
            flash('Email berhasil diubah!', category='success')
            return redirect(request.referrer)
        else:
            flash('Kata sandi salah, silakan coba lagi!', category='danger')
            return redirect(url_for('personal.settings')) 

@personal.route('/dashboard/pengaturan/<int:id>/update-password', methods=['GET', 'POST'])
@login_required
def updatepassword(id):
    user = User.query.get_or_404(id)
    oldpass = request.form['old-pass']
    newpass = request.form['new-pass']
    confnewpass = request.form['new-pass-conf']

    if request.method == 'POST':
        if check_password_hash(current_user.password, oldpass):
            if confnewpass != newpass:
                flash('Konfirmasi kata sandi tidak cocok!', 'danger')
            else:
                user.password = generate_password_hash(newpass)
                db.session.commit()
                flash('Kata sandi berhasil diperbarui!', category='success')
                return redirect((request.referrer)) 
        else:
            flash('Kata sandi salah, silakan coba lagi!', category='danger')
            return redirect(url_for('personal.settings'))