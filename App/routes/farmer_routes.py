from flask import Blueprint, flash, render_template, redirect, url_for, current_app, request
from flask_login import login_required, current_user

farmer = Blueprint('farmer', __name__)

@farmer.route('/petani')
@login_required
def index():
    return render_template('farmer/index.html')