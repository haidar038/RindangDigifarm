import requests, google.generativeai as genai, os, markdown2

from flask import Blueprint, render_template, url_for, redirect, request, jsonify, flash, json
from textwrap import shorten
from babel.numbers import format_currency
from datetime import datetime, timedelta

from App.models import Artikel, User, Kebun, DataPangan

public = Blueprint('public', __name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Constants for API parameters
PROVINCE_ID = 32  # Maluku Utara
REGENCY_ID = 1  # Ternate
COMMODITY_ID = 7  # Cabai Merah Besar
PRICE_TYPE_ID = 1
JENIS_ID = 1
PERIOD_ID = 1

# Constants for API endpoint and commodity mapping
API_URL = "https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1"
COMMODITY_IDS = {
    "Cabai Rawit Merah": "8_16",
    "Cabai Merah Keriting": "7_14",
    "Bawang Merah": "5"
}
PROVINCE_ID = 32

def fetch_red_chili_data(target_date):
    """Fetches price data for 'Cabai Merah Besar' using the specified API.

    Args:
        target_date (str): The target date in "Jan 15, 2025" format.

    Returns:
        dict: A dictionary containing the formatted price for 'Cabai Merah Besar'.
    """
    url = "https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1"
    params = {
        "tanggal": target_date,
        "commodity": f"{COMMODITY_ID}_14",
        "priceType": PRICE_TYPE_ID,
        "isPasokan": 1,
        "jenis": JENIS_ID,
        "periode": PERIOD_ID,
        "provId": PROVINCE_ID,
        "_": int(datetime.now().timestamp() * 1000)
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        print(data)  # Debugging: Tampilkan data respons API

        # Ambil data dari respons
        item = data.get("data", [])[0]  # Ambil item pertama
        if not item:
            return {"error": "Data tidak ditemukan"}

        # Ambil tanggal, nama komoditas, dan nilai harga
        formatted_date = datetime.strptime(item["Tanggal"], "%d %b %y").strftime("%d/%m/%Y")
        formatted_price = format_currency(item["Nilai"], "IDR", locale="id_ID", decimal_quantization=False)[:-3]

        return {
            "date": formatted_date,
            "name": item["Komoditas"],
            "price": formatted_price
        }

    except requests.exceptions.RequestException as e:
        flash(f"Error fetching data: {e}", category='error')
        return {"error": "Error fetching data"}

@public.route('/')
def index():
    kebun = Kebun.query.all()
    produksi = DataPangan.query.filter(DataPangan.is_deleted == False).all()
    articles = Artikel.query.limit(3).all()
    featured_articles = Artikel.query.first()

    # Define target date (today as default)
    target_date = datetime.today().strftime("%b %d, %Y")  # Example: "Jan 15, 2025"
    table_data = fetch_red_chili_data(target_date)

    total_prod = sum(prod.jml_panen for prod in produksi)

    # Maps
    data_kebun = Kebun.query.join(User).all()
    koordinat = []
    
    for kebun_item in data_kebun:
        # Periksa apakah kebun memiliki users yang terkait
        if not kebun_item.users:
            continue
            
        try:
            user = kebun_item.users[0]  # Ambil user pertama
            petani_profile = user.petani_profile if hasattr(user, 'petani_profile') else None
            
            koordinat.append({
                'coords': kebun_item.koordinat,
                'uid': kebun_item.unique_id,
                'nama_kebun_item': kebun_item.nama,
                'luas': kebun_item.luas_kebun,
                'user': {
                    'name': user.nama_lengkap,
                    'profile_pic': user.profile_pic,
                    'profile_id': petani_profile.unique_id if petani_profile else 'N/A',
                    'city': user.kota,
                    'status': 'Aktif' if user.is_confirmed else 'Tidak Aktif'
                }
            })
        except (IndexError, AttributeError) as e:
            # Log error jika diperlukan
            print(f"Error processing kebun {kebun_item.id}: {str(e)}")
            continue

    return render_template('public/index.html', page='home', koordinat=json.dumps(koordinat), kebun=kebun, total_prod=total_prod, articles=articles, featured_articles=featured_articles, shorten=shorten, table_data=table_data)

@public.route('/prakiraan-cuaca')
def weather():
    return render_template('public/weather.html')

@public.route('/harga-komoditas')
def commodity_price():
    return render_template('public/harga_komoditas.html')

# In public_routes.py, add these functions:

def fetch_commodity_data(target_date, commodity_id):
    """Fetches price data for a specific commodity."""
    url = "https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1"
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
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None

@public.route('/api/commodity-prices', methods=['GET'])
def get_commodity_prices():
    target_date = request.args.get('date', datetime.today().strftime("%b %d, %Y"))
    
    all_data = {}
    for commodity_name, commodity_id in COMMODITY_IDS.items():
        data = fetch_commodity_data(target_date, commodity_id)
        if data and data.get('data'):
            item = data['data'][0]
            formatted_date = datetime.strptime(item["Tanggal"], "%d %b %y").strftime("%d/%m/%Y")
            all_data[commodity_name] = {
                "date": formatted_date,
                "price": format_currency(item["Nilai"], "IDR", locale="id_ID", decimal_quantization=False)[:-3]
            }
    
    return jsonify(all_data)

# @public.route('/api/price-data', methods=['GET', 'POST'])
# def get_price_data():
#     kab_kota = request.args.get('kab_kota')
#     komoditas_id = request.args.get('komoditas_id')
#     start_date = request.args.get('start_date')
#     end_date = request.args.get('end_date')

#     url = f"https://panelharga.badanpangan.go.id/data/kabkota-range-by-levelharga/{KAB_KOTA}/{KOMODITAS_ID}/{start_date}/{end_date}"
    
#     try:
#         response = requests.get(url)
#         response.raise_for_status()  # Raise an error for bad responses
#         return jsonify(response.json()), 200
#     except requests.exceptions.RequestException as e:
#         return jsonify({"error": str(e)}), 500

@public.route('/api/gemini', methods=['POST'])
def gemini_api():
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400

    prompt = f"Saya adalah asisten virtual untuk platform agrikultur digital bernama RINDANG, yang membantu petani mengelola produksi pertanian dan memberikan informasi seputar pertanian di Kota Ternate. Saya hanya boleh memberikan jawaban terkait agrikultur, termasuk tetapi tidak terbatas pada: cara merawat tanaman, rekomendasi pupuk, langkah-langkah menghadapi cuaca, dan teknologi pertanian. Pertanyaan pengguna: {user_message}."

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        
        if response and response.text:
            # Convert Markdown to HTML in the backend using markdown2
            assistant_reply = markdown2.markdown(response.text)
        else:
            return jsonify({'error': 'No content received from Gemini API'}), 500

        return jsonify({'reply': assistant_reply}), 200

    except Exception as e:
        print(f"Error communicating with Gemini API: {e}")
        return jsonify({'error': f'Error communicating with Gemini API: {e}'}), 500

@public.route('/rindang-ai')
def rindang_ai():
    return render_template('public/rindang_ai.html')

@public.route('/rindang-pedia')
def rindang_pedia():
    # Add pagination logic
    page = request.args.get('page', 1, type=int)
    pagination_pages = 5  # Same as index page
    articles_pagination = Artikel.query.filter(
        Artikel.is_drafted == False,
        Artikel.is_approved == True
    ).paginate(page=page, per_page=pagination_pages)
    
    articles = articles_pagination.items if articles_pagination.items else []
    
    return render_template('public/rindang_pedia.html', 
                            articles=articles,
                            min=min,
                            max=max,
                            articles_pagination=articles_pagination,
                            shorten=shorten)

@public.route('/read-article/<int:id>', methods=['GET'])
def read_article(id):
    article = Artikel.query.get_or_404(id)
    if article.is_drafted:
        flash('Artikel tidak tersedia!', 'warning')
        return redirect(request.referrer)
    created_by = User.query.filter_by(id=article.created_by).first()
    return render_template('public/article.html', article=article, created_by=created_by.nama_lengkap)

@public.route('/peta-sebaran', methods=['GET', 'POST'])
def maps():
    data_kebun = Kebun.query.join(User).all()
    koordinat = []
    
    for kebun in data_kebun:
        # Periksa apakah kebun memiliki users yang terkait
        if not kebun.users:
            continue
            
        try:
            user = kebun.users[0]  # Ambil user pertama
            petani_profile = user.petani_profile if hasattr(user, 'petani_profile') else None
            
            koordinat.append({
                'coords': kebun.koordinat,
                'uid': kebun.unique_id,
                'nama_kebun': kebun.nama,
                'luas': kebun.luas_kebun,
                'user': {
                    'name': user.nama_lengkap,
                    'profile_pic': user.profile_pic,
                    'profile_id': petani_profile.unique_id if petani_profile else 'N/A',
                    'city': user.kota,
                    'status': 'Aktif' if user.is_confirmed else 'Tidak Aktif'
                }
            })
        except (IndexError, AttributeError) as e:
            # Log error jika diperlukan
            print(f"Error processing kebun {kebun.id}: {str(e)}")
            continue
            
    return render_template('public/maps.html', koordinat=json.dumps(koordinat))