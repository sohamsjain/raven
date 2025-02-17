from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.kite import bp
from kite import *


@bp.route('/connect', methods=['GET', 'POST'])
@login_required
def connect():
    print("Creating Kite Object")
    k = Kite()
    print("Kite Object created successfully")

    if request.method == 'POST':
        print("Handling Post Request")
        request_token = request.form.get('request_token')
        print(f"Request Token: {request_token}")
        print(f"Secret Key: {k.api_secret}")
        if request_token:
            # Attempt to create a new session with the request token
            if k.create_session(request_token):
                flash('Successfully connected to Kite!', 'success')
                return redirect(url_for('main.index'))  # Redirect to dashboard or appropriate page
            else:
                flash('Failed to create Kite session. Please try again.', 'error')
                return redirect(url_for('kite.connect'))
        else:
            flash('Request token is required', 'error')
            return redirect(url_for('kite.connect'))

    login_url = k.get_login_url()
    print(login_url)
    return render_template("kiteconnect.html",
                           title="Kite Connect",
                           logged_in=k.logged_in,
                           login_url=login_url)
