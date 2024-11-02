from flask import Blueprint, render_template, redirect, url_for, flash, request

expert = Blueprint('expert', __name__)

@expert.route('/ahli')
def index():
    return render_template('expert/index.html')