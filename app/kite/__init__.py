from flask import Blueprint

bp = Blueprint('kite', __name__)

from app.kite import routes



