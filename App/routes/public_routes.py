import requests, google.generativeai as genai, os, markdown2

from flask import Blueprint, render_template, url_for, redirect, request, jsonify, flash, json, current_app, session, abort
from flask_login import login_required, current_user
from textwrap import shorten
from babel.numbers import format_currency
from datetime import datetime, timedelta

from App import db
from App.services.xendit_client import XenditClient, XenditError
from App.models import Artikel, User, Kebun, DataPangan, OrderItem, Order, Product, Transaction, Komoditas

public = Blueprint('public', __name__)

# Constants for API parameters
API_URL = "https://www.bi.go.id/hargapangan/WebSite/Home/GetGridData1"
PROVINCE_ID = 32  # Maluku Utara
REGENCY_ID = 1  # Ternate
COMMODITY_ID = 7  # Cabai Merah Besar
PRICE_TYPE_ID = 1
JENIS_ID = 1
PERIOD_ID = 1

# Commodity mapping for API
COMMODITY_IDS = {
    "Cabai Rawit Merah": "8_16",
    "Cabai Merah Keriting": "7_14",
    "Bawang Merah": "5"
}

# Xendit webhook token
WEBHOOK_TOKEN = os.getenv('XENDIT_WEBHOOK_KEY')

def fetch_commodity_data(target_date, commodity_id=None, format_response=True):
    """Fetches price data for commodities using the specified API.

    Args:
        target_date (str): The target date in "Jan 15, 2025" format.
        commodity_id (str, optional): The commodity ID to fetch. If None, defaults to Cabai Merah Besar.
        format_response (bool, optional): Whether to format the response or return raw data. Defaults to True.

    Returns:
        dict: A dictionary containing the formatted price data or raw API response.
    """
    # Use default commodity (Cabai Merah Besar) if none specified
    if commodity_id is None:
        commodity_id = f"{COMMODITY_ID}_14"  # Default to Cabai Merah Besar

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

    response = requests.get(API_URL, params=params)
    response.raise_for_status()
    data = response.json()

    # If raw data requested, return it directly
    if not format_response:
        return data
    
    # Format the response
    data_list = data.get("data")
    # Pastikan data_list adalah list dan punya paling tidak satu elemen
    if not isinstance(data_list, list) or len(data_list) == 0:
        return {"error": "Data tidak ditemukan", "price": "-"}

    try:
        item = data_list[0]
        raw = item.get("Tanggal", "")
        parts = raw.split()
        if len(parts) != 3:
            raise ValueError(f"Format tanggal tak terduga: {raw}")
        day, mon_id, yy = parts

        # Map Indonesian month abbreviation to numeric month
        MONTHS = {
            'Jan':'01','Feb':'02','Mar':'03','Apr':'04',
            'Mei':'05','Jun':'06','Jul':'07','Agu':'08',
            'Sep':'09','Okt':'10','Nov':'11','Des':'12'
        }
        if mon_id not in MONTHS:
            raise ValueError(f"Unknown month abbreviation: {mon_id}")

        yyyy = '20' + yy                # "25" → "2025"
        formatted_date = f"{day}/{MONTHS[mon_id]}/{yyyy}"

        # Format price
        formatted_price = format_currency(
            item.get("Nilai", 0), "IDR",
            locale="id_ID", decimal_quantization=False
        )[:-3]

        return {
            "date": formatted_date,
            "name": item.get("Komoditas", "-"),
            "price": formatted_price
        }

    except (IndexError, TypeError, ValueError) as e:
        current_app.logger.warning(f"Error parsing API data: {e}")
        return {"error": "Gagal memproses data", "price": "-"}

@public.route('/')
def index():
    kebun = Kebun.query.all()
    produksi = DataPangan.query.filter(DataPangan.is_deleted == False).all() or []
    articles = Artikel.query.filter(
        Artikel.is_drafted == False,
        Artikel.is_approved == True
    ).limit(3).all()
    featured_articles = Artikel.query.filter(
        Artikel.is_drafted == False,
        Artikel.is_approved == True
    ).first()

    # Define target date (today as default)
    # Menghindari NoneType error
    target_date = datetime.today().strftime("%b %d, %Y")
    table_data = fetch_commodity_data(target_date)

    total_prod = sum(prod.jml_panen for prod in produksi if prod.jml_panen is not None)

    # Maps
    data_kebun = Kebun.query.join(User).all() or []
    koordinat = []

    for kebun_item in data_kebun:
        if not kebun_item.users:
            continue
        try:
            user = kebun_item.users[0]  # Ambil user pertama
            petani_profile = user.petani_profile if hasattr(user, 'petani_profile') else None

            komoditas_list = kebun_item.komoditas.split(',') if kebun_item.komoditas else []

            koordinat.append({
                'coords': kebun_item.koordinat,
                'uid': kebun_item.unique_id,
                'nama_kebun_item': kebun_item.nama,
                'luas': kebun_item.luas_kebun,
                'komoditas': komoditas_list,  # Tambahkan daftar komoditas
                'user': {
                    'name': user.nama_lengkap,
                    'profile_pic': user.profile_pic,
                    'profile_id': petani_profile.unique_id if petani_profile else 'N/A',
                    'city': user.kota,
                    'status': 'Aktif' if user.is_confirmed else 'Tidak Aktif'
                }
            })
        except (IndexError, AttributeError) as e:
            current_app.logger.error(f"Error processing kebun {kebun_item.id}: {str(e)}")
            continue

    return render_template('public/index.html',
                            page='home',
                            koordinat=json.dumps(koordinat),
                            kebun=kebun,
                            total_prod=total_prod,
                            articles=articles,
                            featured_articles=featured_articles,
                            shorten=shorten,
                            table_data=table_data)
@public.route('/prakiraan-cuaca')
def weather():
    return render_template('public/weather.html')

@public.route('/harga-komoditas')
def commodity_price():
    return render_template('public/harga_komoditas.html')

@public.route('/api/commodity-prices', methods=['GET'])
def get_commodity_prices():
    """Get prices for all commodities defined in COMMODITY_IDS."""
    target_date = request.args.get('date', datetime.today().strftime("%b %d, %Y"))

    all_data = {}
    for commodity_name, commodity_id in COMMODITY_IDS.items():
        # Use the unified fetch_commodity_data function with format_response=False to get raw data
        data = fetch_commodity_data(target_date, commodity_id, format_response=False)
        if data and data.get('data'):
            item = data['data'][0]
            # Format the date consistently
            try:
                formatted_date = datetime.strptime(item["Tanggal"], "%d %b %y").strftime("%d/%m/%Y")
                all_data[commodity_name] = {
                    "date": formatted_date,
                    "price": format_currency(item["Nilai"], "IDR", locale="id_ID", decimal_quantization=False)[:-3]
                }
            except (ValueError, KeyError) as e:
                current_app.logger.error(f"Error formatting commodity data for {commodity_name}: {str(e)}")
                continue

    return jsonify(all_data)



def configure_gemini():
    """Configure Gemini API with fallback handling"""
    api_key = os.getenv('GEMINI_API_KEY') or current_app.config.get('GEMINI_API_KEY')
    if api_key:
        genai.configure(api_key=api_key)
        return True
    else:
        current_app.logger.warning("GEMINI_API_KEY not found in environment")
        return False

@public.before_app_request
def init_gemini():
    """Initialize Gemini configuration before first request"""
    configure_gemini()

@public.route('/api/gemini', methods=['POST'])
def gemini_api():
    """Handle Gemini AI API requests for agricultural assistance."""
    # Ensure Gemini is configured
    if not configure_gemini():
        return jsonify({'error': 'Gemini API not configured'}), 503

    # Validate input
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400

    try:
        # Create model and generate response
        model = genai.GenerativeModel("gemini-2.5-flash")

        # Define the system prompt for agricultural assistance
        prompt = (
            "Saya adalah asisten virtual untuk platform agrikultur digital bernama RINDANG, "
            "yang membantu petani mengelola produksi pertanian dan memberikan informasi "
            "seputar pertanian di Maluku Utara. Saya hanya boleh memberikan jawaban terkait "
            "agrikultur, termasuk tetapi tidak terbatas pada: cara merawat tanaman, rekomendasi pupuk, "
            "langkah-langkah menghadapi cuaca, dan teknologi pertanian. "
            f"Pertanyaan pengguna: {user_message}."
        )

        # Generate content
        response = model.generate_content(prompt)

        # Process response
        if response and response.text:
            assistant_reply = markdown2.markdown(response.text)
            return jsonify({'reply': assistant_reply}), 200

        return jsonify({'error': 'No content received from AI model'}), 500

    except Exception as e:
        current_app.logger.error(f"Gemini API error: {str(e)}")
        return jsonify({'error': 'Service temporarily unavailable'}), 503

@public.route('/rindang-ai')
def rindang_ai():
    return render_template('public/rindang_ai.html')

@public.route('/rindang-market')
def rindang_market():
    """Halaman katalog—tampilkan produk aktif dengan pagination."""
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 8  # Show 8 products per page

    # Get filter parameters
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', '')
    category = request.args.get('category', '')

    # Base query - active products only
    query = Product.query.filter_by(is_active=True)

    # Apply search filter if provided
    if search_query:
        query = query.filter(
            db.or_(
                Product.nama.ilike(f'%{search_query}%'),
                Product.deskripsi.ilike(f'%{search_query}%')
            )
        )

    # Apply category filter if provided
    if category and category.isdigit():
        query = query.filter(Product.komoditas_id == int(category))

    # Apply sorting
    if sort_by == 'price-asc':
        query = query.order_by(Product.harga.asc())
    elif sort_by == 'price-desc':
        query = query.order_by(Product.harga.desc())
    elif sort_by == 'name-asc':
        query = query.order_by(Product.nama.asc())
    elif sort_by == 'name-desc':
        query = query.order_by(Product.nama.desc())
    else:
        # Default sorting - newest first
        query = query.order_by(Product.created_at.desc())

    # Execute query with pagination
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    # Get all categories for filter dropdown
    categories = db.session.query(Komoditas).all()

    # Get cart from session
    cart = session.get('cart')

    return render_template(
        'public/rindang_market.html',
        products=products,
        pagination=pagination,
        cart=cart,
        fc=format_currency,
        search_query=search_query,
        sort_by=sort_by,
        category=category,
        categories=categories
    )

@public.route('/rindang-market/product/<int:id>')
def rindang_product_detail(id):
    p = Product.query.get_or_404(id)
    return render_template('public/rindang_product.html', product=p)

@public.route('/rindang-market/cart/add', methods=['POST'])
@login_required
def cart_add():
    """Simpan di session simple cart sebelum checkout."""
    prod_id = request.form.get('product_id', type=int)
    qty = request.form.get('quantity', type=int, default=1)

    # Validate product exists and has enough stock
    product = Product.query.get_or_404(prod_id)
    if product.stok < qty:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': f'Stok tidak cukup untuk {product.nama}'
            }), 400
        else:
            flash(f'Stok tidak cukup untuk {product.nama}', 'danger')
            return redirect(url_for('public.rindang_market'))

    # Add to cart
    cart = session.setdefault('cart', {})
    cart[str(prod_id)] = cart.get(str(prod_id), 0) + qty
    session.modified = True

    # Return appropriate response based on request type
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': 'Produk ditambahkan ke keranjang',
            'cart_count': len(cart)
        })
    else:
        flash('Produk ditambahkan ke keranjang', 'success')
        return redirect(url_for('public.rindang_market'))

@public.route('/rindang-market/cart')
@login_required
def cart_view():
    """View cart contents."""
    cart = session.get('cart', {})
    items = []
    total = 0
    for pid, qty in cart.items():
        p = Product.query.get(int(pid))
        if not p: continue
        subtotal = p.harga * qty
        items.append({'product':p,'qty':qty,'subtotal':subtotal})
        total += subtotal
    return render_template('public/rindang_cart.html', items=items, total=total)

@public.route('/rindang-market/cart/update', methods=['POST'])
@login_required
def cart_update():
    """Update cart item quantity."""
    prod_id = request.form.get('product_id', type=int)
    qty = request.form.get('quantity', type=int)

    # Validate inputs
    if not prod_id or qty is None:
        return jsonify({
            'success': False,
            'message': 'Invalid request parameters'
        }), 400

    # Get cart from session
    cart = session.get('cart', {})

    # Handle quantity changes
    if qty > 0:
        # Validate product exists and has enough stock
        product = Product.query.get_or_404(prod_id)
        if product.stok < qty:
            return jsonify({
                'success': False,
                'message': f'Stok tidak cukup untuk {product.nama}'
            }), 400

        # Update quantity
        cart[str(prod_id)] = qty
        message = 'Jumlah produk diperbarui'
    else:
        # Remove item from cart
        if str(prod_id) in cart:
            del cart[str(prod_id)]
        message = 'Produk dihapus dari keranjang'

    # Save changes
    session.modified = True

    # Calculate new totals
    items = []
    total = 0
    for pid, item_qty in cart.items():
        p = Product.query.get(int(pid))
        if not p: continue
        subtotal = p.harga * item_qty
        items.append({'product': p, 'qty': item_qty, 'subtotal': subtotal})
        total += subtotal

    # Format total for display
    formatted_total = format_currency(total, "IDR", locale="id_ID", decimal_quantization=False)[:-3]

    # Return response
    return jsonify({
        'success': True,
        'message': message,
        'cart_count': len(cart),
        'cart_total': formatted_total,
        'item_subtotal': format_currency(product.harga * qty, "IDR", locale="id_ID", decimal_quantization=False)[:-3] if qty > 0 else 0
    })

@public.route('/rindang-market/order/<int:order_id>/payment-info', methods=['GET'])
@login_required
def order_payment_info(order_id):
    """Get payment info for an order"""
    # Ambil order, pastikan milik user saat ini
    order = Order.query.get_or_404(order_id)
    if order.buyer_id != current_user.id:
        abort(403)

    # Tentukan metode dan data pembayaran
    if order.status == 'pending':
        method = 'va'
    else:
        method = 'qris'

    return jsonify({
        'method': method,
        'payment_data': order.payment_qris,
        'payment_method': order.payment_method,
        'payment_id': order.payment_id,
        'total_amount': float(order.total_amount),
        'status': order.status
    })

@public.route('/api/orders/<int:order_id>/status', methods=['GET'])
@login_required
def get_order_status(order_id):
    """Get the current status of an order.

    This endpoint is used for real-time status updates on the order detail page.
    """
    try:
        order = Order.query.get_or_404(order_id)

        # Check if user is authorized to view this order
        if order.buyer_id != current_user.id:
            return jsonify({
                'success': False,
                'message': 'Unauthorized'
            }), 403

        # Get the latest transaction for this order
        latest_transaction = Transaction.query.filter_by(
            order_id=order.id
        ).order_by(Transaction.created_at.desc()).first()

        return jsonify({
            'success': True,
            'status': order.status,
            'updated_at': order.updated_at.isoformat() if order.updated_at else None,
            'transaction': {
                'status': latest_transaction.status if latest_transaction else None,
                'created_at': latest_transaction.created_at.isoformat() if latest_transaction else None
            } if latest_transaction else None
        })

    except Exception as e:
        current_app.logger.error(f"Error getting order status: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error retrieving order status'
        }), 500



# Helper functions for payment processing
def create_va_payment(order, total):
    """Create a Virtual Account payment for an order.

    Args:
        order: The Order object
        total: The total amount to pay

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if user has VA bank code set up
        if not hasattr(current_user, 'petani_profile') or not current_user.petani_profile or not current_user.petani_profile.va_bank_code:
            current_app.logger.warning(f"User {current_user.id} has no VA bank code configured")
            return False

        # Create VA through Xendit
        va_data = XenditClient.create_va(
            external_id=f"order-{order.id}",
            bank_code=current_user.petani_profile.va_bank_code,
            name=current_user.nama_lengkap,
            expected_amount=float(total)
        )

        # Store VA details
        order.payment_qris = va_data.get('account_number')  # Store VA number in payment_qris field
        order.payment_id = va_data.get('id')  # Store Xendit payment ID

        # Create transaction record
        transaction = Transaction.create_payment_transaction(
            order=order,
            payment_method='va',
            payment_id=va_data.get('id'),
            status='pending',
            notes=f"VA Payment: {va_data.get('account_number')}"
        )
        db.session.add(transaction)

        current_app.logger.info(f"Created VA payment for order {order.id}: {va_data.get('account_number')}")
        return True

    except Exception as e:
        # Handle Xendit API errors
        flash(f'Gagal membuat Virtual Account: {str(e)}', 'danger')
        current_app.logger.error(f"Failed to create VA for order {order.id}: {str(e)}")
        return False


def create_dynamic_qris(order, seller_id, total):
    """Create a dynamic QRIS payment for an order.

    Args:
        order: The Order object
        seller_id: The ID of the seller
        total: The total amount to pay

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create dynamic QRIS for this specific order
        qr_data = XenditClient.create_qr_code(
            seller_id=seller_id,
            external_id=f"order-{order.id}",
            amount=float(total)
        )

        # Store QRIS details
        order.payment_qris = qr_data.get('qr_string')
        order.payment_id = qr_data.get('id')

        # Create transaction record
        transaction = Transaction.create_payment_transaction(
            order=order,
            payment_method='qris',
            payment_id=qr_data.get('id'),
            status='pending',
            notes="QRIS Payment (Dynamic)"
        )
        db.session.add(transaction)

        current_app.logger.info(f"Created dynamic QRIS for order {order.id}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to create dynamic QR code: {str(e)}")
        return False


def use_seller_qris(order, seller):
    """Use the seller's QRIS code (dynamic or static) for payment.

    Args:
        order: The Order object
        seller: The seller User object

    Returns:
        bool: True if successful, False otherwise
    """
    # Check if seller has dynamic QR enabled in their profile
    if (seller and hasattr(seller, 'petani_profile') and seller.petani_profile and
            seller.petani_profile.qris_dynamic_enabled and seller.petani_profile.qris_dynamic_string):
        # Use the seller's dynamic QR code
        order.payment_qris = seller.petani_profile.qris_dynamic_string
        order.payment_id = seller.petani_profile.qris_dynamic_id

        # Create transaction record
        transaction = Transaction.create_payment_transaction(
            order=order,
            payment_method='qris',
            payment_id=seller.petani_profile.qris_dynamic_id,
            status='pending',
            notes="QRIS Payment (Seller's Dynamic QR)"
        )
        db.session.add(transaction)
        current_app.logger.info(f"Using seller's dynamic QRIS for order {order.id}")
        return True

    # Check if seller has static QR in their profile
    elif seller and hasattr(seller, 'petani_profile') and seller.petani_profile and seller.petani_profile.qris_static:
        # Use the seller's static QR code
        order.payment_qris = seller.petani_profile.qris_static

        # Create transaction record
        transaction = Transaction.create_payment_transaction(
            order=order,
            payment_method='qris',
            status='pending',
            notes="QRIS Payment (Seller's Static QR)"
        )
        db.session.add(transaction)
        current_app.logger.info(f"Using seller's static QRIS for order {order.id}")
        return True

    return False


def create_static_qris(order, seller_id):
    """Create a static QRIS payment for an order.

    Args:
        order: The Order object
        seller_id: The ID of the seller

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create static QRIS
        qr_data = XenditClient.create_qr_code(
            seller_id=seller_id,
            external_id=f"order-{order.id}"
        )

        # Store QRIS details
        order.payment_qris = qr_data.get('qr_string')
        order.payment_id = qr_data.get('id')

        # Create transaction record
        transaction = Transaction.create_payment_transaction(
            order=order,
            payment_method='qris',
            payment_id=qr_data.get('id'),
            status='pending',
            notes="QRIS Payment (Static fallback)"
        )
        db.session.add(transaction)

        current_app.logger.info(f"Created static QRIS fallback for order {order.id}")
        return True

    except Exception as e:
        current_app.logger.error(f"Static QR fallback failed: {str(e)}")
        return False


def use_product_qris(order, product):
    """Use the product's static QRIS code for payment.

    Args:
        order: The Order object
        product: The Product object

    Returns:
        bool: True if successful, False otherwise
    """
    if product and product.qris_static:
        order.payment_qris = product.qris_static

        # Create transaction record
        transaction = Transaction.create_payment_transaction(
            order=order,
            payment_method='qris',
            status='pending',
            notes="QRIS Payment (Product static fallback)"
        )
        db.session.add(transaction)
        current_app.logger.info(f"Using product's static QRIS for order {order.id}")
        return True

    return False


def create_emergency_qris(order):
    """Create an emergency QRIS payment as a last resort.

    Args:
        order: The Order object

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create a basic QR code with just the order ID
        qr_data = XenditClient.create_qr_code(
            seller_id=current_user.id,  # Use buyer as fallback
            external_id=f"order-{order.id}"
        )

        # Store QRIS details
        order.payment_qris = qr_data.get('qr_string')
        order.payment_id = qr_data.get('id')

        # Create transaction record
        transaction = Transaction.create_payment_transaction(
            order=order,
            payment_method='qris',
            payment_id=qr_data.get('id'),
            status='pending',
            notes="QRIS Payment (Emergency fallback)"
        )
        db.session.add(transaction)

        current_app.logger.info(f"Created emergency QRIS fallback for order {order.id}")
        return True

    except Exception as e:
        current_app.logger.error(f"Emergency QR creation failed: {str(e)}")
        return False


def process_qris_payment(order, sellers, total, cart):
    """Process QRIS payment with multiple fallback mechanisms.

    Args:
        order: The Order object
        sellers: Set of seller IDs
        total: The total amount to pay
        cart: The cart dictionary

    Returns:
        bool: True if any payment method was set up, False otherwise
    """
    # Get the main seller (first seller if multiple)
    main_seller_id = list(sellers)[0] if sellers else None

    if main_seller_id:
        # Get seller profile
        seller = User.query.get(main_seller_id)

        # Try dynamic QRIS first (preferred method)
        if create_dynamic_qris(order, main_seller_id, total):
            return True

        # If dynamic QRIS fails, try using seller's existing QRIS
        if use_seller_qris(order, seller):
            return True

        # If seller's QRIS fails, try creating a static QRIS
        if create_static_qris(order, main_seller_id):
            return True

    # If no seller or all seller methods fail, try product QRIS
    try:
        product = Product.query.get(int(list(cart.keys())[0]))
        if use_product_qris(order, product):
            return True
    except (IndexError, ValueError) as e:
        current_app.logger.error(f"Error getting product for QRIS fallback: {str(e)}")

    # Last resort: emergency QRIS
    return create_emergency_qris(order)


@public.route('/rindang-market/checkout', methods=['POST'])
@login_required
def cart_checkout():
    """
    Process checkout from cart

    This function:
    1. Creates an order from the cart
    2. Creates order items
    3. Reduces product stock
    4. Sets up payment method (QRIS or VA)
    5. Creates a transaction record
    6. Clears the cart
    """
    try:
        # Get cart from session
        cart = session.get('cart', {})
        if not cart:
            flash('Keranjang kosong', 'warning')
            return redirect(url_for('public.rindang_market'))

        # Create order
        order = Order(
            buyer_id=current_user.id,
            total_amount=0,
            status='pending'
        )
        db.session.add(order)
        db.session.flush()  # Get order ID without committing

        # Process cart items
        items = []
        total = 0
        sellers = set()  # Track unique sellers

        for pid, qty in cart.items():
            # Get product
            p = Product.query.get(int(pid))
            if not p:
                continue

            # Check stock
            if p.stok < qty:
                flash(f'Stok tidak cukup untuk {p.nama}', 'danger')
                return redirect(url_for('public.cart_view'))

            # Calculate subtotal
            subtotal = p.harga * qty

            # Create order item
            order_item = OrderItem(
                order_id=order.id,
                product_id=p.id,
                quantity=qty,
                unit_price=p.harga
            )
            db.session.add(order_item)

            # Reduce stock
            p.stok -= qty

            # Track for display
            items.append({'product': p, 'qty': qty, 'subtotal': subtotal})
            total += subtotal

            # Track unique sellers
            if p.seller_id:
                sellers.add(p.seller_id)

        # Update order total
        order.total_amount = total

        # Process payment method
        payment_method = request.form.get('payment_method', 'qris')
        order.payment_method = payment_method
        payment_success = False

        # Handle different payment methods
        if payment_method == 'va':
            # Try to create VA payment
            payment_success = create_va_payment(order, total)

            # Fallback to QRIS if VA fails
            if not payment_success:
                payment_method = 'qris'
                order.payment_method = 'qris'

        # Handle QRIS payment (either as primary method or fallback)
        if payment_method == 'qris':
            payment_success = process_qris_payment(order, sellers, total, cart)

        # If all payment methods failed, log the error but still create the order
        if not payment_success:
            current_app.logger.error(f"All payment methods failed for order {order.id}")
            flash('Pembayaran tidak dapat diproses. Silakan hubungi admin.', 'warning')

        # Commit all changes
        db.session.commit()

        # Clear cart
        session.pop('cart', None)

        # Redirect to order detail
        flash('Pesanan berhasil dibuat', 'success')
        return redirect(url_for('public.rindang_order_detail', order_id=order.id))

    except Exception as e:
        # Handle unexpected errors
        db.session.rollback()
        current_app.logger.error(f"Error in checkout: {str(e)}")
        flash('Terjadi kesalahan saat checkout', 'danger')
        return redirect(url_for('public.cart_view'))

# Helper functions for webhook processing
def find_order_from_payment_data(payment_data):
    """Find an order based on payment data from webhook.

    Args:
        payment_data: Dictionary containing payment data from webhook

    Returns:
        Order object or None if not found
    """
    order = None
    payment_id = payment_data.get('id')
    external_id = payment_data.get('external_id', '')
    qr_string = payment_data.get('qr_string')

    # Log all possible identifiers to help with debugging
    current_app.logger.info(
        f"Payment identifiers: payment_id={payment_id}, "
        f"external_id={external_id}, "
        f"qr_string={qr_string[:30] if qr_string else None}"
    )

    # If external_id starts with 'order-', it's a direct order reference
    if external_id and external_id.startswith('order-'):
        try:
            order_id = int(external_id.split('-', 1)[-1])
            order = Order.query.get(order_id)
            if order:
                current_app.logger.info(f"Found order by external_id: {order.id}")
                return order
        except (ValueError, IndexError):
            current_app.logger.error(f"Invalid order ID in external_id: {external_id}")

    # If order not found by external_id, try by payment_id
    if not order and payment_id:
        order = Order.query.filter_by(payment_id=payment_id).first()
        if order:
            current_app.logger.info(f"Found order by payment_id: {order.id}")
            return order

    # If order not found by payment_id, try by qr_string
    if not order and qr_string:
        order = Order.query.filter_by(payment_qris=qr_string).first()
        if order:
            current_app.logger.info(f"Found order by qr_string: {order.id}")
            return order

    return None


def create_seller_notification(seller_id, order_id, buyer_name):
    """Create a notification for the seller about a paid order.

    Args:
        seller_id: ID of the seller
        order_id: ID of the order
        buyer_name: Name of the buyer

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create a notification record
        notification = {
            'user_id': seller_id,
            'type': 'new_order',
            'message': f'Pesanan #{order_id} telah dibayar oleh {buyer_name}',
            'order_id': order_id,
            'created_at': datetime.now().isoformat()
        }

        # Store notification in a temporary file for polling
        notification_dir = os.path.join(current_app.root_path, 'static', 'notifications')
        os.makedirs(notification_dir, exist_ok=True)

        notification_file = os.path.join(notification_dir, f'seller_{seller_id}_notifications.json')

        # Read existing notifications
        notifications = []
        if os.path.exists(notification_file):
            try:
                with open(notification_file, 'r') as f:
                    notifications = json.load(f)
            except json.JSONDecodeError:
                notifications = []

        # Add new notification
        notifications.append(notification)

        # Write back to file
        with open(notification_file, 'w') as f:
            json.dump(notifications, f)

        current_app.logger.info(f"Created notification for seller {seller_id}")
        return True
    except Exception as e:
        current_app.logger.error(f"Error creating notification: {str(e)}")
        return False


def process_paid_payment(data, order):
    """Process a paid payment from webhook.

    Args:
        data: Dictionary containing payment data from webhook
        order: Order object

    Returns:
        bool: True if successful, False otherwise
    """
    # Skip if order already paid
    if order.status == 'paid':
        current_app.logger.warning(f"Order already paid: {order.id}")
        return True

    # Extract payment details
    payment_id = data.get('id')
    amount = float(data.get('amount', 0))

    # Update order status
    order.status = 'paid'
    current_app.logger.info(f"Updating order {order.id} status to 'paid'")

    # Get seller from order items
    seller_id = None
    seller_ids = order.get_seller_ids()

    if not seller_ids:
        current_app.logger.error(f"No seller found for order {order.id}")
        return False

    # Use the first seller for simplicity
    seller_id = seller_ids[0]
    current_app.logger.info(f"Found seller ID: {seller_id} for order {order.id}")

    # Get seller and buyer
    seller = User.query.get(seller_id)
    buyer = User.query.get(order.buyer_id)

    if not buyer or not seller:
        current_app.logger.error(f"User not found: buyer={order.buyer_id}, seller={seller_id}")
        return False

    # Transfer balance from buyer to seller
    buyer.balance = buyer.balance - amount if hasattr(buyer, 'balance') else 0
    seller.balance = seller.balance + amount if hasattr(seller, 'balance') else amount
    current_app.logger.info(f"Transferred {amount} from buyer {buyer.id} to seller {seller.id}")

    # Update transaction status
    transaction = Transaction.query.filter_by(
        order_id=order.id,
        transaction_type='payment'
    ).first()

    if transaction:
        transaction.status = 'completed'
        transaction.updated_at = datetime.now()
        transaction.payment_id = payment_id
        current_app.logger.info(f"Updated existing transaction for order {order.id}")
    else:
        # Create new transaction if not found
        transaction = Transaction(
            order_id=order.id,
            from_user_id=buyer.id,
            to_user_id=seller.id,
            amount=amount,
            transaction_type='payment',
            status='completed',
            payment_method=order.payment_method,
            payment_id=payment_id,
            notes=f"{order.payment_method.upper()} Payment (from webhook)"
        )
        db.session.add(transaction)
        current_app.logger.info(f"Created new transaction for order {order.id}")

    # Send notification to seller
    create_seller_notification(
        seller_id=seller.id,
        order_id=order.id,
        buyer_name=buyer.nama_lengkap or buyer.username
    )

    return True


def process_expired_payment(data, order):
    """Process an expired payment from webhook.

    Args:
        data: Dictionary containing payment data from webhook (not used directly but kept for consistency)
        order: Order object

    Returns:
        bool: True if successful, False otherwise
    """
    # data parameter is not used directly but kept for consistency with other webhook processing functions
    # Skip if order not in pending state
    if order.status != 'pending':
        current_app.logger.warning(f"Order not in pending state: {order.id}, current state: {order.status}")
        return True

    # Update order status
    order.status = 'expired'
    current_app.logger.info(f"Updating order {order.id} status to 'expired'")

    # Update transaction status if exists
    transaction = Transaction.query.filter_by(
        order_id=order.id,
        transaction_type='payment',
        status='pending'
    ).first()

    if transaction:
        transaction.status = 'failed'
        transaction.updated_at = datetime.now()
        transaction.notes = f"{transaction.notes} (Expired)"
        current_app.logger.info(f"Updated transaction for expired order {order.id}")

    return True


@public.route('/api/xendit/webhook', methods=['POST'])
def xendit_webhook():
    """
    Handle Xendit payment callbacks

    This endpoint receives callbacks from Xendit when a payment is made.
    It verifies the callback token, processes the payment, and updates the order status.
    """
    # Verify callback token
    token = request.headers.get('x-callback-token')
    webhook_token = current_app.config.get('XENDIT_WEBHOOK_KEY', 'test_webhook_token')

    if token != webhook_token:
        current_app.logger.warning(f"Invalid Xendit callback token: {token}")
        abort(403, 'Invalid callback token')

    try:
        data = request.get_json()
        current_app.logger.info(f"Received Xendit webhook: {data}")

        # Get payment status
        status = data.get('status')

        # Add retry mechanism for database operations
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Find the order
                order = find_order_from_payment_data(data)

                if not order:
                    current_app.logger.warning(f"Order not found for payment with status: {status}")
                    break  # Exit retry loop as no action needed

                # Process based on status
                if status == 'PAID':
                    if process_paid_payment(data, order):
                        db.session.commit()
                        current_app.logger.info(f"Payment processed for order {order.id}")
                        break  # Exit retry loop on success

                elif status == 'EXPIRED':
                    if process_expired_payment(data, order):
                        db.session.commit()
                        current_app.logger.info(f"Payment expired for order {order.id}")
                        break  # Exit retry loop on success

                else:
                    # Unhandled status
                    current_app.logger.info(f"Unhandled webhook status: {status}")
                    break  # Exit retry loop as no action needed

            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    current_app.logger.error(f"Failed to process webhook after {max_retries} retries: {str(e)}")
                    # Don't raise the exception - we want to return 200 to Xendit
                    break
                else:
                    current_app.logger.warning(f"Retry {retry_count}/{max_retries} for webhook processing: {str(e)}")
                    db.session.rollback()  # Roll back the transaction before retrying
                    import time
                    time.sleep(1)  # Wait a second before retrying

        return '', 200  # Always return 200 to Xendit

    except Exception as e:
        current_app.logger.error(f"Error processing Xendit webhook: {str(e)}")
        # Don't return an error to Xendit - they'll retry
        return '', 200

@public.route('/rindang-market/order/<int:order_id>/simulate-payment', methods=['POST'])
@login_required
def simulate_payment(order_id):
    """Simulate payment for testing purposes"""
    # Check if we're in test mode
    is_test_mode = current_app.config.get('XENDIT_MODE', 'test') == 'test'

    if not is_test_mode:
        flash('Simulasi pembayaran hanya tersedia dalam mode test', 'warning')
        return redirect(url_for('public.rindang_order_detail', order_id=order_id))

    # Get the order
    order = Order.query.get_or_404(order_id)

    # Verify the order belongs to the current user
    if order.buyer_id != current_user.id:
        flash('Anda tidak memiliki akses ke pesanan ini', 'danger')
        return redirect(url_for('public.rindang_market'))

    # Verify the order is still pending
    if order.status != 'pending':
        flash('Hanya pesanan dengan status pending yang dapat disimulasikan pembayarannya', 'warning')
        return redirect(url_for('public.rindang_order_detail', order_id=order_id))

    try:
        # Simulate payment based on payment method
        if order.payment_method == 'qris':
            # For QRIS, we need the QR ID or external_id
            if order.payment_id:
                # If we have a payment ID, use it directly
                qr_id = order.payment_id
            else:
                # Otherwise, construct an external_id
                qr_id = f"order-{order.id}"

            # Log the QR details for debugging
            current_app.logger.info(f"Simulating payment for order {order.id} with QR ID: {qr_id}")
            if order.payment_qris:
                current_app.logger.info(f"Order has QR string: {order.payment_qris[:30]}...")

            # Simulate payment
            result = XenditClient.simulate_payment(
                qr_id=qr_id,
                amount=float(order.total_amount)
            )

            # Log the result
            current_app.logger.info(f"Simulated QRIS payment for order {order.id}: {result}")

            # Update order status (webhook might not be triggered in test mode)
            order.status = 'paid'

            # Update transaction
            transaction = Transaction.query.filter_by(
                order_id=order.id,
                transaction_type='payment'
            ).first()

            if transaction:
                transaction.status = 'completed'
                transaction.updated_at = datetime.now()
                transaction.notes = f"{transaction.notes} (Simulated)"

            db.session.commit()

            flash('Pembayaran QRIS berhasil disimulasikan', 'success')

        elif order.payment_method == 'va':
            # For VA, we would need to call a different Xendit API
            # This is a placeholder - Xendit might have a different method for VA simulation

            # Update order status manually for simulation
            order.status = 'paid'

            # Update transaction
            transaction = Transaction.query.filter_by(
                order_id=order.id,
                transaction_type='payment'
            ).first()

            if transaction:
                transaction.status = 'completed'
                transaction.updated_at = datetime.now()
                transaction.notes = f"{transaction.notes} (Simulated)"

            db.session.commit()

            flash('Pembayaran Virtual Account berhasil disimulasikan', 'success')

        return redirect(url_for('public.rindang_order_detail', order_id=order.id))

    except XenditError as e:
        flash(f'Gagal mensimulasikan pembayaran: {e.message}', 'danger')
        return redirect(url_for('public.rindang_order_detail', order_id=order.id))
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
        return redirect(url_for('public.rindang_order_detail', order_id=order.id))

@public.route('/rindang-market/order/<int:order_id>')
@login_required
def rindang_order_detail(order_id):
    order = Order.query.get_or_404(order_id)

    # Check if we're in test mode
    is_test_mode = current_app.config.get('XENDIT_MODE', 'test') == 'test'

    return render_template('public/rindang_order.html', order=order, is_test_mode=is_test_mode)

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

@public.route('/maintenance')
def maintenance():
    return render_template('public/maintenance.html')
