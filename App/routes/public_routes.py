import requests, google.generativeai as genai, os, markdown2

from flask import Blueprint, render_template, url_for, redirect, request, jsonify, flash
from textwrap import shorten

from App.models import Artikel, User

public = Blueprint('public', __name__)

# Constants for API URL parameters
KAB_KOTA = 458  # Ternate
KOMODITAS_ID = 3
TARGET_KOMODITAS = ["Cabai Merah Keriting", "Cabai Rawit Merah", "Bawang Merah"]

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

@public.route('/')
def index():
    return render_template('public/index.html', page='home')

@public.route('/prakiraan-cuaca')
def weather():
    return render_template('public/weather.html')

@public.route('/harga-komoditas')
def commodity_price():
    return render_template('public/harga_komoditas.html')

@public.route('/api/price-data', methods=['GET', 'POST'])
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
    articles = Artikel.query.all()
    return render_template('public/rindang_pedia.html', articles=articles, shorten=shorten)

@public.route('/read-article/<int:id>', methods=['GET'])
def read_article(id):
    article = Artikel.query.get_or_404(id)
    if article.is_drafted:
        flash('Artikel tidak tersedia!', 'warning')
        return redirect(request.referrer)
    created_by = User.query.filter_by(id=article.created_by).first()
    return render_template('public/article.html', article=article, created_by=created_by.nama_lengkap)