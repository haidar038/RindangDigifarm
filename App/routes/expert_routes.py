from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from datetime import datetime
from functools import wraps

from App import db
from App.models import User, Forum

expert = Blueprint('expert', __name__)

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_role('ahli') or not current_user.is_confirmed:
                flash(f'Hanya {role} yang dapat memiliki izin untuk mengakses halaman ini!', 'warning')
                return redirect(url_for('public.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@expert.route('/ahli')
@login_required
@role_required('ahli')
def index():
    replied = Forum.query.filter(Forum.is_replied == True).filter(Forum.created_by != current_user.id).count()
    unreplied = Forum.query.filter(Forum.is_replied == False).filter(Forum.created_by != current_user.id).count()
    total_users = User.query.filter(User.username != 'admin').count()
    return render_template('expert/index.html', replied=replied, unreplied=unreplied, total_users=total_users)

@expert.route('/ahli/forum')
@login_required
@role_required('ahli')
def forum():
    # Get filter parameters
    search = request.args.get('search', '')
    time_filter = request.args.get('time_filter', '')
    status_filter = request.args.get('status_filter', '')
    
    # Get page parameter for pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of items per page
    
    # Base query
    query = Forum.query.join(User, Forum.created_by == User.id).filter(Forum.created_by != current_user.id)
    
    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                Forum.question.ilike(f'%{search}%')
            )
        )
    
    # Apply time filter
    if time_filter == 'newest':
        query = query.order_by(Forum.created_at.desc())
    elif time_filter == 'latest':
        query = query.order_by(Forum.created_at.asc())
        
    # Apply status filter
    if status_filter == 'terjawab':
        query = query.filter(Forum.answer != None)
    elif status_filter == 'belum_terjawab':
        query = query.filter(Forum.answer == None)
    
    # Execute paginated query
    questions = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template(
        'expert/manajemen_forum.html',
        questions=questions,
        User=User,
        search=search,
        time_filter=time_filter,
        status_filter=status_filter
    )

@expert.route('/ahli/forum/answer/<int:question_id>', methods=['POST'])
@login_required
@role_required('ahli')
def answer_question(question_id):
    question = Forum.query.get_or_404(question_id)
    answer = request.form.get('ckeditor')  # Ambil jawaban dari form CKEditor
    
    question.answer = answer
    question.replied_at = datetime.now()
    question.replied_by = current_user.id
    
    db.session.commit()
    
    flash('Jawaban berhasil disimpan', 'success')
    return redirect(url_for('expert.forum'))