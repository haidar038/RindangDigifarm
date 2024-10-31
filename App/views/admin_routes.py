from flask import Blueprint, render_template, redirect, url_for

admin = Blueprint('admin', __name__)

@admin.route('/admin')
def index():
    return render_template('admin/index.html')