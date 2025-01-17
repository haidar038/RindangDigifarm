import requests, random, string, os, secrets

from flask import Blueprint, flash, render_template, json, redirect, url_for, current_app, request, jsonify, send_file
from flask_login import login_required, current_user
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from datetime import datetime, date, timedelta
from babel.numbers import format_currency
from babel.dates import format_date
from werkzeug.utils import secure_filename
from typing import Optional, Tuple
from openpyxl import load_workbook
from functools import wraps
from io import BytesIO

from App import db
from App.models import Kebun, DataPangan, KebunKomoditas, Komoditas

farmer = Blueprint('farmer', __name__)

# Constants for API URL parameters
KAB_KOTA = 458  # Ternate
KOMODITAS_ID = 3
TARGET_KOMODITAS = ["Cabai Merah Keriting", "Cabai Rawit Merah", "Bawang Merah"]
REPORT_ALLOWED_EXTENSIONS = {'xlsx'}
PICTURE_ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Constants for fetching price data from API
API_URL = "https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1"
COMMODITY_IDS = {
    "Cabai Rawit Merah": "8_16",
    "Cabai Merah Keriting": "7_14",
    "Bawang Merah": "5"
}
PRICE_TYPE_ID = 1
JENIS_ID = 1
PERIOD_ID = 1
PROVINCE_ID = 32

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_role('petani') or not current_user.is_confirmed:
                flash(f'Hanya {role} yang dapat memiliki izin untuk mengakses halaman ini!', 'warning')
                return redirect(url_for('public.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def picture_allowed_file(filename):
    return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in PICTURE_ALLOWED_EXTENSIONS

def report_allowed_file(filename):
    return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in REPORT_ALLOWED_EXTENSIONS

def generate_unique_id(prefix="KR_", string_length=2, number_length=4):
    """
    Generates a unique ID in the format KR_AB1234.

    Args:
        prefix: The static identifier prefix (default: "KR_").
        string_length: The length of the random string part (default: 2).
        number_length: The length of the random number part (default: 4).

    Returns:
        A unique ID string.
    """
    random_string = ''.join(random.choices(string.ascii_uppercase, k=string_length))
    random_number = ''.join(random.choices(string.digits, k=number_length))
    unique_id = f"{prefix}{random_string}{random_number}"
    return unique_id

# Helper function to fetch commodity data from API
def fetch_commodity_data(target_date, commodity_id):
    params = {
        "tanggal": target_date,
        "commodity": commodity_id,
        "priceType": PRICE_TYPE_ID,
        "isPasokan": 1,
        "jenis": JENIS_ID,
        "periode": PERIOD_ID,
        "provId": PROVINCE_ID,
        "_": int(datetime.now().timestamp() * 1000)
    }
    
    try:
        response = requests.get(API_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

# Helper function to fetch and format price data from API
def fetch_price_data(start_date, end_date):
    """Fetches price data from the API and formats it for display.

    Args:
        start_date (str): The starting date in YYYY-MM-DD format.
        end_date (str): The ending date in YYYY-MM-DD format.

    Returns:
        list: A list of dictionaries containing formatted price data.
    """

    url = f"https://panelharga.badanpangan.go.id/data/kabkota-range-by-levelharga/{KAB_KOTA}/{KOMODITAS_ID}/{start_date}/{end_date}"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors

        data = response.json()

        table_data = []
        for item in data["data"]:
            if item["name"] in TARGET_KOMODITAS:
                for date_data in item["by_date"]:
                    date_obj = datetime.strptime(date_data["date"], "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d/%m/%Y")
                    geomean_value = date_data["geomean"]

                    # Menyederhanakan format harga
                    formatted_price = "-" if geomean_value == "-" else format_currency(float(geomean_value), "IDR", locale="id_ID", decimal_quantization=False)[:-3]

                    table_data.append({
                        "date": formatted_date,
                        "name": item["name"],
                        "price": formatted_price
                    })

        return table_data

    except requests.exceptions.RequestException as e:
        flash(f"Error fetching data: {e}", category='error')
        return []  # Return an empty list on error

@farmer.route('/api/productivity/cabai-rawit', methods=['GET'])
def get_cabai_productivity():
    try:
        # Get latest harvests for Cabai Rawit Merah
        cabai_harvests = (db.session.query(DataPangan)
            .join(Komoditas)
            .filter(
                Komoditas.nama == 'Cabai Rawit',
                DataPangan.tanggal_panen.isnot(None),
                DataPangan.jml_panen.isnot(None)
            )
            .order_by(DataPangan.tanggal_panen.desc())
            .limit(2)
            .all())

        if len(cabai_harvests) < 2:
            return jsonify({'productivity': 0, 'trend': 'none'})

        # Latest harvest is first due to DESC order
        current_harvest = cabai_harvests[0].jml_panen
        previous_harvest = cabai_harvests[1].jml_panen

        if previous_harvest <= 0:
            return jsonify({'productivity': 0, 'trend': 'none'})

        productivity = ((current_harvest - previous_harvest) / previous_harvest * 100)
        
        return jsonify({
            'productivity': round(productivity, 1),
            'trend': 'up' if productivity > 0 else 'down' if productivity < 0 else 'none'
        })
    except Exception as e:
        current_app.logger.error(f"Error calculating productivity: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@farmer.route('/api/calendar-data', methods=['GET'])
def get_calendar_data():
    try:
        plantings = (db.session.query(DataPangan)
            .join(Kebun)
            .join(Komoditas)
            .filter(
                DataPangan.tanggal_bibit.isnot(None),
                DataPangan.is_deleted == False,
                DataPangan.status == 'Penanaman',  # Only show plantings that haven't been harvested
                DataPangan.user_id == current_user.id
            )
            .all())

        calendar_data = []
        today = datetime.now().date()
        
        for planting in plantings:
            estimated_harvest = planting.tanggal_bibit + timedelta(days=60)
            days_remaining = (estimated_harvest - today).days
            
            if days_remaining > 0:  # Only include future harvests
                calendar_data.append({
                    'date': estimated_harvest.isoformat(),
                    'kebun': planting.kebun.nama,
                    'komoditas': planting.komoditas_info.nama,
                    'days_remaining': days_remaining
                })

        return jsonify(calendar_data)
    except Exception as e:
        current_app.logger.error(f"Error getting calendar data: {str(e)}")
        return jsonify([])

@farmer.route('/api/daily-productivity/cabai-rawit', methods=['GET'])
def get_daily_productivity():
    try:
        # Get all harvests for Cabai Rawit Merah
        harvests = (db.session.query(DataPangan)
            .join(Komoditas)
            .filter(
                Komoditas.nama == 'Cabai Rawit',
                DataPangan.tanggal_panen.isnot(None),
                DataPangan.jml_panen.isnot(None)
            )
            .order_by(DataPangan.tanggal_panen)
            .all())

        productivity_data = []
        for i in range(1, len(harvests)):
            current = harvests[i].jml_panen
            previous = harvests[i-1].jml_panen
            
            if previous > 0:
                change = ((current - previous) / previous * 100)
                productivity_data.append({
                    'date': harvests[i].tanggal_panen.isoformat(),
                    'value': round(change, 1)
                })

        return jsonify(productivity_data)
    except Exception as e:
        current_app.logger.error(f"Error getting productivity data: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@farmer.route('/api/get-price-data', methods=['GET'])
def getpricedata():
    target_date = datetime.today().strftime("%b %d, %Y")
    all_data = []
    
    for commodity_name, commodity_id in COMMODITY_IDS.items():
        data = fetch_commodity_data(target_date, commodity_id)
        if data and data.get('data'):
            item = data['data'][0]
            formatted_date = datetime.strptime(item["Tanggal"], "%d %b %y").strftime("%d/%m/%Y")
            all_data.append({
                "date": formatted_date,
                "name": commodity_name,
                "price": format_currency(item["Nilai"], "IDR", locale="id_ID", decimal_quantization=False)[:-3]
            })
    
    return jsonify(all_data)

@farmer.route('/api/price-data', methods=['GET', 'POST'])
def get_price_data():
    kab_kota = request.args.get('kab_kota')
    komoditas_id = request.args.get('komoditas_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    url = f"https://panelharga.badanpangan.go.id/data/kabkota-range-by-levelharga/{KAB_KOTA}/{KOMODITAS_ID}/{start_date}/{end_date}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        return jsonify(response.json()), 200
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@farmer.route('/petani')
@login_required
@role_required('petani')
def index():
    # Query existing
    data_pangan = DataPangan.query.filter_by(
        user_id=current_user.id,
        status='Penanaman',
        is_deleted=False
    ).all()
    
    # Query untuk menghitung produktivitas
    harvested_data = DataPangan.query.filter(
        DataPangan.user_id == current_user.id,
        DataPangan.status == 'Panen',
        DataPangan.is_deleted == False,
        DataPangan.jml_panen.isnot(None),
        DataPangan.tanggal_panen.isnot(None)
    ).order_by(DataPangan.tanggal_panen.desc()).limit(2).all()

    # Hitung perubahan produktivitas
    productivity_change = 0
    if len(harvested_data) >= 2:
        current_harvest = harvested_data[0].jml_panen
        previous_harvest = harvested_data[1].jml_panen
        if previous_harvest > 0:  # Hindari pembagian dengan nol
            productivity_change = ((current_harvest - previous_harvest) / previous_harvest) * 100
    
    # Total panen (dari kode yang sudah ada)
    all_data = DataPangan.query.filter_by(
        user_id=current_user.id,
        is_deleted=False
    ).all()
    total_panen = sum(prod.jml_panen for prod in all_data if prod.jml_panen)

    # Kode untuk harvest_data tetap sama
    today = date.today()
    harvest_data = []
    next_harvest_days = None
    
    for estPanen in data_pangan:
        if estPanen.estimasi_panen:
            est_date = datetime.strptime(estPanen.estimasi_panen.strftime('%Y-%m-%d'), '%Y-%m-%d').date()
            days_remaining = (est_date - today).days
            if days_remaining > 0:
                harvest_data.append({
                    'date': estPanen.estimasi_panen,
                    'days_remaining': days_remaining,
                    'kebun': estPanen.kebun.nama,
                    'komoditas': estPanen.komoditas_info.nama
                })
                if next_harvest_days is None or days_remaining < next_harvest_days:
                    next_harvest_days = days_remaining

    return render_template('farmer/index.html',
                            total_panen=total_panen,
                            harvest_data=json.dumps(harvest_data),
                            next_harvest_days=next_harvest_days,
                            productivity_change=round(productivity_change, 1),
                            page='farmer_index')

@farmer.route('/petani/manajemen-produksi', methods=['GET', 'POST'])
@login_required
@role_required('petani')
def manajemen_produksi():
    kebun = Kebun.query.filter_by(user_id=current_user.id, is_deleted=False).all()
    komoditas = Komoditas.query.filter_by(is_deleted=False).all()

    # Ambil parameter filter dari request
    field_id = request.args.get('field')
    commodity_id = request.args.get('commodity')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Pagination parameters
    page = request.args.get('page', 1, type=int)  # Default to page 1
    per_page = request.args.get('per_page', 10, type=int)  # Default to 10 items per page

    # Ambil data produksi 3 bulan terakhir, termasuk yang masih dalam status "Penanaman"
    three_months_ago = datetime.now() - timedelta(days=90)
    query = DataPangan.query.filter(
        DataPangan.user_id == current_user.id,
        DataPangan.is_deleted == False,
        DataPangan.tanggal_bibit >= three_months_ago
    )

    # Terapkan filter jika ada
    if field_id:
        query = query.filter(DataPangan.kebun_id == field_id)
    if commodity_id:
        query = query.filter(DataPangan.komoditas_id == commodity_id)
    if start_date:
        query = query.filter(DataPangan.tanggal_bibit >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(DataPangan.tanggal_bibit <= datetime.strptime(end_date, '%Y-%m-%d'))

    # Pagination
    produksi = query.paginate(page=page, per_page=per_page)

    # Hitung total akumulasi produksi
    total_produksi = sum(prod.jml_panen for prod in produksi.items if prod.jml_panen is not None)

    # Format data untuk chart
    chart_data = []
    for prod in produksi.items:
        chart_data.append({
            'kebun': prod.kebun.nama,
            'komoditas': prod.komoditas_info.nama,
            'tanggal_panen': format_date(prod.tanggal_panen, format='d MMM Y', locale='id') if prod.tanggal_panen else None,
            'hasil_panen': prod.jml_panen
        })

    # Hitung persentase perubahan produktivitas
    productivity_changes = {}
    for kom in komoditas:
        panen_data = sorted(
            [p for p in produksi.items if p.komoditas_id == kom.id and p.tanggal_panen is not None],
            key=lambda x: x.tanggal_panen
        )
        if len(panen_data) >= 2:
            current = panen_data[-1].jml_panen
            previous = panen_data[-2].jml_panen
            change = ((current - previous) / previous * 100) if previous > 0 else 0
            productivity_changes[kom.id] = {
                'persentase': round(change, 2),
                'trend': 'up' if change >= 0 else 'down'
            }

    user_data = {
        'nama_lengkap': current_user.nama_lengkap,
        'kelurahan': current_user.kelurahan,
        'kota': current_user.kota,
        'luas_lahan': sum(kebun.luas_kebun for kebun in current_user.kebun) 
    }

    print(current_user.kebun)

    return render_template('farmer/manajemen_produksi.html',
                            kebun=kebun,
                            komoditas=komoditas,
                            produksi=produksi,
                            total_produksi=total_produksi,
                            chart_data=json.dumps(chart_data),
                            productivity_changes=productivity_changes,
                            format_date=format_date,
                            user_data=user_data,
                            page='farmer_manajemen_produksi'
                            )

def save_kebun_photo(photo_file) -> Tuple[bool, str]:
    """
    Save uploaded kebun photo and return status and filename
    """
    try:
        if not photo_file or photo_file.filename == '':
            return True, ''

        if not picture_allowed_file(photo_file.filename):
            return False, 'Format file tidak diizinkan!'
        
        filename = secrets.token_hex(8) + '_' + secure_filename(photo_file.filename)
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'foto_kebun')
        os.makedirs(upload_folder, exist_ok=True)
        photo_file.save(os.path.join(upload_folder, filename))
        return True, filename

    except Exception as e:
        current_app.logger.error(f"Error saving kebun photo: {str(e)}")
        return False, 'Gagal menyimpan foto'

def validate_kebun_data(nama: str, user_id: int) -> Optional[str]:
    """
    Validate kebun data and return error message if invalid
    """
    if not nama or not nama.strip():
        return 'Nama kebun tidak boleh kosong'
        
    existing_kebun = Kebun.query.filter_by(nama=nama, user_id=user_id, is_deleted=False).first()
    if existing_kebun:
        return 'Nama kebun sudah ada, silakan gunakan nama lain'
    
    return None

@farmer.route('/api/komoditas')
def get_komoditas():
    komoditas = Komoditas.query.filter_by(is_deleted=False).all()
    return jsonify([{
        'id': k.id,
        'nama': k.nama,
        'kategori': k.kategori
    } for k in komoditas])

@farmer.route('/petani/informasi-kebun')
@login_required
@role_required('petani')
def informasi_kebun():
    """Get all active gardens for current user"""
    try:
        kebun = Kebun.query.filter_by(
            user_id=current_user.id,
            is_deleted=False
        ).order_by(Kebun.created_at.desc()).all()
        return render_template('farmer/informasi_kebun.html', kebun=kebun, page='farmer_informasi_kebun')
    except SQLAlchemyError as e:
        current_app.logger.error(f"Database error in informasi_kebun: {str(e)}")
        flash('Terjadi kesalahan saat mengambil data kebun', 'error')
        return redirect(url_for('main.dashboard'))

def handle_komoditas_input(komoditas_names):
    """
    Handle komoditas input and ensure they exist in database
    Returns list of Komoditas objects
    """
    komoditas_objects = []
    
    for nama in komoditas_names:
        if not nama:  # Skip empty names
            continue
            
        # Check if komoditas already exists
        komoditas = Komoditas.query.filter_by(
            nama=nama,
            is_deleted=False
        ).first()
        
        if not komoditas:
            # Create new komoditas if it doesn't exist
            komoditas = Komoditas(
                nama=nama,
                kategori='Lainnya',  # Default category, can be modified as needed
                created_by=current_user.id
            )
            db.session.add(komoditas)
            try:
                db.session.flush()  # Flush to get the ID without committing
            except SQLAlchemyError as e:
                current_app.logger.error(f"Error creating komoditas: {str(e)}")
                db.session.rollback()
                continue
                
        komoditas_objects.append(komoditas)
    
    return komoditas_objects

def create_kebun_komoditas(kebun, komoditas_list, luas_tanam=None):
    """
    Create KebunKomoditas relationships for given kebun and komoditas list
    """
    for komoditas in komoditas_list:
        kebun_komoditas = KebunKomoditas(
            kebun_id=kebun.id,
            komoditas_id=komoditas.id,
            luas_tanam=luas_tanam,  # You might want to handle individual luas_tanam later
            is_active=True,
            added_at=datetime.now()
        )
        db.session.add(kebun_komoditas)

@farmer.route('/petani/informasi-kebun/tambah-kebun', methods=['GET', 'POST'])
@login_required
@role_required('petani')
def add_kebun():
    """Add new garden with proper relationship initialization"""
    if request.method == 'POST':
        try:
            # Validate input data
            nama = request.form.get('nama_kebun')
            error_message = validate_kebun_data(nama, current_user.id)
            if error_message:
                flash(error_message, 'warning')
                return redirect(url_for('farmer.informasi_kebun'))

            # Handle komoditas input
            komoditas = request.form.getlist('komoditas[]')
            komoditas_lainnya = request.form.get('komoditas_lainnya')
            
            if komoditas_lainnya:
                komoditas.append(komoditas_lainnya)
            
            # Remove empty values and duplicates
            komoditas = list(filter(None, set(komoditas)))
            
            # Handle photo uploads
            uploaded_photos = request.files.getlist('fotoKebun[]')
            if not uploaded_photos or uploaded_photos[0].filename == '':
                result = 'default_thumbnail.jpg'
            else:
                filenames = []
                for photo in uploaded_photos:
                    if photo and photo.filename != '':
                        success, filename = save_kebun_photo(photo)
                        if not success:
                            flash(filename, 'danger')
                            return redirect(request.url)
                        filenames.append(filename)
                result = ','.join(filenames)

            # Begin transaction
            # 1. Create or get Komoditas objects
            komoditas_objects = handle_komoditas_input(komoditas)
            
            if not komoditas_objects:
                flash('Minimal satu komoditas harus dipilih', 'warning')
                return redirect(request.url)

            # 2. Create new Kebun
            new_kebun = Kebun(
                user_id=current_user.id,
                nama=nama,
                luas_kebun=request.form.get('luaskebun'),
                foto=result,
                komoditas=','.join(komoditas),  # Keep this for backward compatibility
                koordinat=request.form.get('koordinat'),
                unique_id=generate_unique_id()
            )
            new_kebun.users.append(current_user)
            
            db.session.add(new_kebun)
            db.session.flush()  # Get the ID without committing
            
            # 3. Create KebunKomoditas relationships
            create_kebun_komoditas(new_kebun, komoditas_objects)
            
            # 4. Commit all changes
            db.session.commit()
            
            flash('Kebun Berhasil Ditambahkan!', 'success')
            return redirect(url_for('farmer.informasi_kebun'))

        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.error(f"Integrity error in add_kebun: {str(e)}")
            flash('Data kebun tidak valid', 'danger')
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error in add_kebun: {str(e)}")
            flash('Gagal menambahkan kebun', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Unexpected error in add_kebun: {str(e)}")
            flash('Terjadi kesalahan sistem', 'danger')
        
    return redirect(request.referrer)

@farmer.route('/petani/informasi-kebun/update/<int:id>', methods=['POST'])
@login_required
@role_required('petani')
def update_kebun(id: int):
    """Update existing garden"""
    try:
        kebun = Kebun.query.get_or_404(id)
        
        # Check authorization
        if current_user not in kebun.users:
            flash('Anda tidak memiliki akses untuk mengubah kebun ini', 'danger')
            return redirect(url_for('farmer.informasi_kebun'))
        
        # Validate new name
        new_name = request.form.get('nama_kebun')
        if kebun.nama != new_name:  # Only check if name is being changed
            error_message = validate_kebun_data(new_name, current_user.id)
            if error_message:
                flash(error_message, 'warning')
                return redirect(url_for('farmer.informasi_kebun'))
        kebun.nama = new_name

        # Update luas kebun
        kebun.luas_kebun = request.form.get('luaskebun')

        # Update koordinat
        kebun.koordinat = request.form.get('koordinat')

        # Update komoditas
        komoditas = request.form.getlist('komoditas[]')
        komoditas_lainnya = request.form.get('komoditas_lainnya')
        if komoditas_lainnya:
            komoditas.append(komoditas_lainnya)
        kebun.komoditas = ','.join(komoditas)

        # Optionally, handle photo uploads if you want to allow updating photos
        # For simplicity, we can skip updating photos here

        db.session.commit()
        flash('Data Kebun Berhasil diubah!', 'success')
        return redirect(url_for('farmer.informasi_kebun'))

    except IntegrityError:
        db.session.rollback()
        flash('Data kebun tidak valid', 'danger')
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error in update_kebun: {str(e)}")
        flash('Gagal mengubah data kebun', 'danger')
    return redirect(url_for('farmer.informasi_kebun'))

@farmer.route('/petani/informasi-kebun/import_kebun', methods=['POST'])
@login_required
@role_required('petani')
def import_kebun():
    """Import multiple gardens from Excel file"""
    if 'excel_file' not in request.files:
        flash('Tidak ada file yang dipilih!', 'error')
        return redirect(request.url)
        
    excel_file = request.files['excel_file']
    if excel_file.filename == '' or not report_allowed_file(excel_file.filename):
        flash('File tidak valid. Unggah file Excel (.xlsx)!', 'error')
        return redirect(request.url)

    try:
        wb = load_workbook(excel_file)
        sheet = wb.active
        
        # Begin transaction
        added_kebun = 0
        skipped_kebun = 0
        
        for row in sheet.iter_rows(min_row=2):
            nama_kebun = row[0].value
            if not nama_kebun:  # Skip empty rows
                continue
                
            # Validate garden name
            error_message = validate_kebun_data(nama_kebun, current_user.id)
            if error_message:
                skipped_kebun += 1
                continue
            
            # Create new garden
            new_kebun = Kebun(
                nama=nama_kebun,
                koordinat=f"{row[2].value}, {row[1].value}",  # longitude, latitude
                luas_kebun=row[3].value,
                user_id=current_user.id,
                unique_id=generate_unique_id()
            )
            new_kebun.users.append(current_user)
            db.session.add(new_kebun)
            added_kebun += 1
            
        db.session.commit()
        
        message = f'Berhasil mengimpor {added_kebun} kebun'
        if skipped_kebun > 0:
            message += f' ({skipped_kebun} kebun dilewati karena duplikat)'
        flash(message, 'success')
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error importing kebun: {str(e)}")
        flash('Gagal mengimpor data. Pastikan format file sesuai template.', 'error')
    
    return redirect(url_for('farmer.informasi_kebun'))

@farmer.route('/petani/informasi-kebun/delete_kebun/<int:id>', methods=['POST', 'GET'])
@login_required
@role_required('petani')
def del_kebun(id):
    """Soft delete garden"""
    try:
        kebun = Kebun.query.get_or_404(id)
        
        # Mengecek authorization
        if current_user not in kebun.users:
            flash('Anda tidak diizinkan menghapus kebun ini', 'danger')
            return redirect(url_for('farmer.informasi_kebun'))
        
        # Soft 'delete' untuk data kebun
        kebun.is_deleted = True
        kebun.deleted_at = datetime.now()
        
        # Menghapus semua user yang terkait
        kebun.users.clear()
        
        db.session.commit()
        flash('Kebun Berhasil Dihapus!', 'danger')
        
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error in del_kebun: {str(e)}")
        flash('Gagal menghapus kebun ', 'danger')
        
    return redirect(url_for('farmer.informasi_kebun'))

@farmer.route('/petani/produksi/tambah', methods=['GET', 'POST'])
@login_required
@role_required('petani')
def tambah_produksi():
    if request.method == 'POST':
        try:
            kebun_id = request.form.get('kebun_id')
            komoditas_id = request.form.get('komoditas_id')
            jml_bibit = request.form.get('jml_bibit')
            tanggal_bibit = request.form.get('tanggal_bibit')

            # Validasi input
            if not kebun_id or not komoditas_id or not jml_bibit or not tanggal_bibit:
                flash('Semua kolom harus diisi!', 'warning')
                return redirect(request.url)

            # Konversi dan validasi tanggal
            try:
                tanggal_bibit = datetime.strptime(tanggal_bibit, '%Y-%m-%d')
                # Hitung estimasi panen 60 hari setelah tanggal bibit
                estimasi_panen = tanggal_bibit + timedelta(days=60)
            except ValueError:
                flash('Format tanggal tidak valid!', 'warning')
                return redirect(request.url)

            # Validasi jumlah bibit
            if not jml_bibit.isdigit() or int(jml_bibit) <= 0:
                flash('Jumlah bibit harus berupa angka positif!', 'warning')
                return redirect(request.url)

            produksi = DataPangan(
                kebun_id=kebun_id,
                komoditas_id=komoditas_id,
                user_id=current_user.id,
                jml_bibit=int(jml_bibit),
                tanggal_bibit=tanggal_bibit,
                estimasi_panen=estimasi_panen,
                status='Penanaman'
            )
            db.session.add(produksi)
            db.session.commit()
            flash('Data produksi berhasil ditambahkan!', 'success')
            return redirect(url_for('farmer.manajemen_produksi'))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error in tambah_produksi: {str(e)}")
            flash('Gagal menambahkan data produksi', 'danger')
    return redirect(request.referrer)

@farmer.route('/petani/produksi/update_produksi/<int:id>', methods=['POST', 'GET'])
@login_required
@role_required('petani')
def update_produksi(id):
    produksi = DataPangan.query.get_or_404(id)
    if request.method == 'POST':
        try:
            # Ambil nilai dari form
            jml_bibit = request.form.get('update_jml_bibit')
            tanggal_bibit = request.form.get('update_tanggal_bibit')
            estimasi_panen = request.form.get('update_estimasi_panen')

            # Konversi tanggal bibit
            produksi.tanggal_bibit = datetime.strptime(tanggal_bibit, '%Y-%m-%d')

            # Validasi dan konversi estimasi panen jika ada
            if estimasi_panen:
                produksi.estimasi_panen = datetime.strptime(estimasi_panen, '%Y-%m-%d')

            # Update status dan jumlah bibit
            produksi.jml_bibit = jml_bibit

            db.session.commit()
            flash('Data produksi berhasil diperbarui!', 'success')
            return redirect(url_for('farmer.manajemen_produksi'))  # Kembali ke halaman manajemen produksi
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error in update_produksi: {str(e)}")
            flash('Gagal memperbarui data produksi', 'danger')
    return redirect(url_for('farmer.manajemen_produksi'))  # Jika bukan POST, kembali ke halaman manajemen produksi

@farmer.route('/petani/produksi/update_panen/<int:id>', methods=['POST', 'GET'])
@login_required
@role_required('petani')
def update_panen(id):
    produksi = DataPangan.query.get_or_404(id)
    if request.method == 'POST':
        try:
            jml_panen = request.form.get('hasil_panen')
            tanggal_panen = request.form.get('tanggal_panen')
            print(tanggal_panen)

            # Mengubah format tanggal panen
            produksi.tanggal_panen = datetime.strptime(tanggal_panen, '%Y-%m-%d')  # Pastikan format tanggal sesuai

            # Update status dan jumlah bibit
            produksi.jml_panen = jml_panen
            produksi.status = 'Panen'

            db.session.commit()
            flash('Data produksi berhasil diperbarui!', 'success')
            return redirect(url_for('farmer.manajemen_produksi'))  # Kembali ke halaman manajemen produksi
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(f"Database error in update_panen: {str(e)}")
            flash('Gagal memperbarui data produksi', 'danger')
    return redirect(url_for('farmer.manajemen_produksi'))  # Jika bukan POST, kembali ke halaman manajemen produksi


@farmer.route('/petani/produksi/delete', methods=['POST', 'GET'])
@login_required
@role_required('petani')
def delete_produksi():
    try:
        delete_ids = request.form.getlist('check')  # Ambil daftar ID dari checkbox yang dipilih
        if not delete_ids:
            flash('Tidak ada data yang dipilih untuk dihapus', 'warning')
            return redirect(url_for('farmer.manajemen_produksi'))
            
        # Soft delete untuk semua ID yang dipilih
        DataPangan.query.filter(
            DataPangan.id.in_(delete_ids),
            DataPangan.user_id == current_user.id  # Pastikan hanya data milik user yang bisa dihapus
        ).update({DataPangan.is_deleted: True}, synchronize_session=False)
        
        db.session.commit()
        flash('Data produksi berhasil dihapus!', 'success')
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error in delete_produksi: {str(e)}")
        flash('Gagal menghapus data produksi', 'danger')
    return redirect(url_for('farmer.manajemen_produksi'))

@farmer.route('/petani/produksi/delete/<int:id>', methods=['POST', 'GET'])
@login_required
@role_required('petani')
def delete_single_produksi(id):
    try:
        produksi = DataPangan.query.get_or_404(id)  # Pastikan ID valid
        produksi.is_deleted = True  # Soft delete
        # db.session.delete(produksi)  # Hapus baris ini jika menggunakan soft delete
        db.session.commit()
        flash('Data produksi berhasil dihapus!', 'warning')
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error(f"Database error in delete_produksi: {str(e)}")
        flash('Gagal menghapus data produksi', 'danger')
    return redirect(url_for('farmer.manajemen_produksi'))

@farmer.route('/api/produksi', methods=['GET'])
@login_required
@role_required('petani')
def api_produksi():
    field_id = request.args.get('field')
    commodity_id = request.args.get('commodity')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    three_months_ago = datetime.now() - timedelta(days=90)
    query = DataPangan.query.filter(
        DataPangan.user_id == current_user.id,
        DataPangan.is_deleted == False,
        DataPangan.tanggal_bibit >= three_months_ago
    )

    if field_id:
        query = query.filter(DataPangan.kebun_id == field_id)
    if commodity_id:
        query = query.filter(DataPangan.komoditas_id == commodity_id)
    if start_date:
        query = query.filter(DataPangan.tanggal_bibit >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(DataPangan.tanggal_bibit <= datetime.strptime(end_date, '%Y-%m-%d'))

    produksi = query.order_by(DataPangan.tanggal_panen.asc()).all()  

    # Enhanced chart data with additional fields
    chart_data = []
    for prod in produksi:
        if prod.tanggal_panen and prod.jml_panen:  # Only include complete records
            chart_data.append({
                'kebun': prod.kebun.nama,
                'komoditas': prod.komoditas_info.nama,
                'tanggal_panen': prod.tanggal_panen.strftime('%Y-%m-%d'),  # Keep date in sortable format
                'hasil_panen': prod.jml_panen
            })

    return jsonify(chart_data)

@farmer.route('/petani/produksi/cetak-laporan', methods=['GET'])
@login_required
@role_required('petani')
def cetak_laporan_produksi():
    try:
        # Query data produksi
        three_months_ago = datetime.now() - timedelta(days=90)
        produksi = DataPangan.query.filter(
            DataPangan.user_id == current_user.id,
            DataPangan.is_deleted == False,
            DataPangan.tanggal_bibit >= three_months_ago
        ).order_by(DataPangan.tanggal_bibit.desc()).all()

        # Buat buffer untuk PDF
        buffer = BytesIO()
        
        # Buat dokumen PDF
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=30
        )
        
        # Daftar elemen yang akan ditambahkan ke PDF
        elements = []
        
        # Tambahkan judul
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30
        )
        elements.append(Paragraph("Laporan Hasil Penanaman - Panen", title_style))
        
        # Persiapkan data untuk tabel
        data = [['Kebun', 'Jumlah Bibit', 'Tanggal Bibit', 'Status', 'Hasil Panen']]
        
        for p in produksi:
            hasil_panen = f"{p.jml_panen}kg, {format_date(p.tanggal_panen, format='d MMM Y', locale='id')}" if p.jml_panen and p.tanggal_panen else "Belum panen"
            data.append([
                p.kebun.nama,
                str(p.jml_bibit),
                format_date(p.tanggal_bibit, format='d MMM Y', locale='id') if p.tanggal_bibit else "-",
                p.status,
                hasil_panen
            ])
        
        # Buat tabel
        table = Table(data, colWidths=[120, 80, 100, 80, 120])
        
        # Style tabel
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
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        elements.append(table)
        
        # Buat PDF
        doc.build(elements)
        
        # Siapkan file untuk didownload
        buffer.seek(0)
        return send_file(
            buffer,
            download_name=f'laporan_produksi_{datetime.now().strftime("%Y%m%d")}.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        current_app.logger.error(f"Error generating PDF: {str(e)}")
        flash('Gagal membuat laporan PDF', 'error')
        return redirect(url_for('farmer.manajemen_produksi'))

@farmer.route('/api/export-csv', methods=['GET'])
@login_required
@role_required('petani')
def export_csv():
    # Similar query as api_produksi but returns CSV formatted data
    query = DataPangan.query.filter(
        DataPangan.user_id == current_user.id,
        DataPangan.is_deleted == False
    )
    
    produksi = query.all()
    
    csv_data = []
    for prod in produksi:
        csv_data.append({
            'kebun': prod.kebun.nama,
            'komoditas': prod.komoditas_info.nama,
            'tanggal_bibit': prod.tanggal_bibit.strftime('%Y-%m-%d') if prod.tanggal_bibit else '',
            'jml_bibit': prod.jml_bibit,
            'tanggal_panen': prod.tanggal_panen.strftime('%Y-%m-%d') if prod.tanggal_panen else '',
            'jml_panen': prod.jml_panen if prod.jml_panen else ''
        })
    
    return jsonify(csv_data)