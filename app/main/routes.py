from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.models import Alert, Ticker, Zone, db
from app.model_service import AlertManager, ZoneManager
from app.main import bp


@bp.route('/')
@bp.route('/index')
def index():
    # Redirect to signup for new users, or alerts for logged-in users
    if current_user.is_authenticated:
        return redirect(url_for('main.alerts'))
    return redirect(url_for('auth.signup'))


@bp.route('/api/tickers/search')
@login_required
def search_tickers():
    query = request.args.get('q', '').upper()
    if len(query) < 1:
        return jsonify({'tickers': []})

    tickers = Ticker.query.filter(Ticker.symbol.like(f'{query}%')).limit(10).all()
    return jsonify({
        'tickers': [{
            'symbol': ticker.symbol,
            'last_price': ticker.last_price
        } for ticker in tickers]
    })


@bp.route('/alerts')
@login_required
def alerts():
    alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.created_at.desc()).all()
    return render_template('alerts.html', alerts=alerts)


@bp.route('/api/alerts')
@login_required
def get_alerts():
    print('alerts requested')
    alerts = Alert.query.filter_by(user_id=current_user.id).order_by(Alert.created_at.desc()).all()
    return jsonify({
        'alerts': [{
            'id': alert.id,
            'symbol': alert.symbol,
            'type': alert.type,
            'price': alert.price,
            'status': alert.status,
            'created_at': alert.created_at.isoformat(),
            'last_price': alert.ticker.last_price if alert.ticker else None
        } for alert in alerts]
    })


@bp.route('/api/alerts/create', methods=['POST'])
@login_required
def create_alert():
    try:
        data = request.get_json()

        # Get or create ticker
        ticker = Ticker.query.filter_by(symbol=data['symbol']).first()
        if not ticker:
            return jsonify({'error': 'Invalid symbol'}), 400

        alert = AlertManager.create_alert(
            user=current_user,
            ticker=ticker,
            alert_type=data['type'],
            price=data['price']
        )

        return jsonify({
            'message': 'Alert created successfully',
            'alert': {
                'id': alert.id,
                'symbol': alert.symbol,
                'type': alert.type,
                'price': alert.price,
                'status': alert.status,
                'created_at': alert.created_at.isoformat(),
                'last_price': alert.ticker.last_price if alert.ticker else None
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@bp.route('/api/alerts/<int:alert_id>', methods=['DELETE'])
@login_required
def delete_alert(alert_id):
    try:
        alert = Alert.query.get_or_404(alert_id)

        # Check if the alert belongs to the current user
        if alert.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        if AlertManager.delete_alert(alert_id):
            return jsonify({'message': 'Alert deleted successfully'}), 200
        return jsonify({'error': 'Alert not found'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@bp.route('/api/alerts/<int:alert_id>', methods=['PUT'])
@login_required
def update_alert(alert_id):
    try:
        alert = Alert.query.get_or_404(alert_id)

        # Check if the alert belongs to the current user
        if alert.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json()
        updated_alert = AlertManager.update_alert(
            alert_id=alert_id,
            alert_type=data.get('type'),
            price=data.get('price')
        )

        if updated_alert:
            return jsonify({
                'message': 'Alert updated successfully',
                'alert': {
                    'id': updated_alert.id,
                    'symbol': updated_alert.symbol,
                    'type': updated_alert.type,
                    'price': updated_alert.price,
                    'status': updated_alert.status,
                    'created_at': updated_alert.created_at.isoformat(),
                    'last_price': updated_alert.ticker.last_price if updated_alert.ticker else None
                }
            }), 200
        return jsonify({'error': 'Alert not found'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@bp.route('/zones')
@login_required
def zones():
    zones = Zone.query.filter_by(user_id=current_user.id).order_by(Zone.created_at.desc()).all()
    return render_template('zones.html', zones=zones)


@bp.route('/api/zones')
@login_required
def get_zones():
    zones = Zone.query.filter_by(user_id=current_user.id).order_by(Zone.created_at.desc()).all()
    return jsonify({
        'zones': [{
            'id': zone.id,
            'symbol': zone.symbol,
            'type': zone.type,
            'entry': zone.entry,
            'stoploss': zone.stoploss,
            'target': zone.target,
            'status': zone.status,
            'created_at': zone.created_at.isoformat(),
            'entry_at': zone.entry_at.isoformat() if zone.entry_at else None,
            'target_at': zone.target_at.isoformat() if zone.target_at else None,
            'stoploss_at': zone.stoploss_at.isoformat() if zone.stoploss_at else None,
            'failed_at': zone.failed_at.isoformat() if zone.failed_at else None,
            'last_price': zone.ticker.last_price if zone.ticker else None
        } for zone in zones]
    })


@bp.route('/api/zones/create', methods=['POST'])
@login_required
def create_zone():
    try:
        data = request.get_json()

        # Get or create ticker
        ticker = Ticker.query.filter_by(symbol=data['symbol']).first()
        if not ticker:
            return jsonify({'error': 'Invalid symbol'}), 400

        zone = ZoneManager.create_zone(
            user=current_user,
            ticker=ticker,
            zone_type=data['type'],
            entry=data['entry'],
            stoploss=data['stoploss'],
            target=data['target']
        )

        return jsonify({
            'message': 'Zone created successfully',
            'zone': {
                'id': zone.id,
                'symbol': zone.symbol,
                'type': zone.type,
                'entry': zone.entry,
                'stoploss': zone.stoploss,
                'target': zone.target,
                'status': zone.status,
                'created_at': zone.created_at.isoformat(),
                'last_price': zone.ticker.last_price if zone.ticker else None
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@bp.route('/api/zones/<int:zone_id>', methods=['DELETE'])
@login_required
def delete_zone(zone_id):
    try:
        zone = Zone.query.get_or_404(zone_id)

        # Check if the zone belongs to the current user
        if zone.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        if ZoneManager.delete_zone(zone_id):
            return jsonify({'message': 'Zone deleted successfully'}), 200
        return jsonify({'error': 'Zone not found'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@bp.route('/api/zones/<int:zone_id>', methods=['PUT'])
@login_required
def update_zone(zone_id):
    try:
        zone = Zone.query.get_or_404(zone_id)

        # Check if the zone belongs to the current user
        if zone.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json()
        updated_zone = ZoneManager.update_zone(
            zone_id=zone_id,
            entry=data.get('entry'),
            stoploss=data.get('stoploss'),
            target=data.get('target')
        )

        if updated_zone:
            return jsonify({
                'message': 'Zone updated successfully',
                'zone': {
                    'id': updated_zone.id,
                    'symbol': updated_zone.symbol,
                    'type': updated_zone.type,
                    'entry': updated_zone.entry,
                    'stoploss': updated_zone.stoploss,
                    'target': updated_zone.target,
                    'status': updated_zone.status,
                    'created_at': updated_zone.created_at.isoformat(),
                    'last_price': updated_zone.ticker.last_price if updated_zone.ticker else None
                }
            }), 200
        return jsonify({'error': 'Zone not found'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400