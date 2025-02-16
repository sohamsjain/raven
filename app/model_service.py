from datetime import datetime, timezone
from typing import Optional, List
from app import db
from app.models import Alert, Zone, AlertType, AlertStatus, ZoneType, ZoneStatus, User, Ticker


class AlertManager:
    @staticmethod
    def create_alert(user: User, ticker: Ticker,
                     alert_type: str, price: float) -> Alert:
        """Create a new alert"""
        alert = Alert(
            user_id=user.id,
            ticker_id=ticker.id,
            symbol=ticker.symbol,
            type=alert_type,
            price=price,
            status=AlertStatus.ACTIVE
        )
        db.session.add(alert)
        db.session.commit()
        return alert

    @staticmethod
    def update_alert(alert_id: int, alert_type: Optional[str] = None,
                     price: Optional[float] = None) -> Optional[Alert]:
        """Update an existing alert"""
        alert = db.session.get(Alert, alert_id)
        if alert:
            if alert_type is not None:
                alert.type = alert_type
            if price is not None:
                alert.price = price
            db.session.commit()
        return alert

    @staticmethod
    def delete_alert(alert_id: int) -> bool:
        """Delete an alert"""
        alert = db.session.get(Alert, alert_id)
        if alert:
            db.session.delete(alert)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_active_alerts_for_ticker(ticker_id: int) -> List[Alert]:
        """Get all active alerts for a specific ticker"""
        return Alert.query.filter_by(
            ticker_id=ticker_id,
            status=AlertStatus.ACTIVE
        ).all()

    @staticmethod
    def check_alert(alert: Alert, current_price: float) -> bool:
        """
        Check if an alert should be triggered based on current price
        Returns True if alert was triggered, False otherwise
        """
        triggered = False

        if alert.status != AlertStatus.ACTIVE:
            return False

        if alert.type == AlertType.CROSS_OVER:
            triggered = current_price >= alert.price
        elif alert.type == AlertType.CROSS_UNDER:
            triggered = current_price <= alert.price

        if triggered:
            alert.status = AlertStatus.TRIGGERED
            alert.triggered_at = datetime.now(timezone.utc)
            db.session.commit()

        return triggered


class ZoneManager:
    @staticmethod
    def create_zone(user: User, ticker: Ticker,
                    zone_type: str, entry: float, stoploss: float,
                    target: float) -> Zone:
        """Create a new trading zone"""
        zone = Zone(
            user_id=user.id,
            ticker_id=ticker.id,
            symbol=ticker.symbol,
            type=zone_type,
            entry=entry,
            stoploss=stoploss,
            target=target,
            status=ZoneStatus.ACTIVE
        )
        db.session.add(zone)
        db.session.commit()
        return zone

    @staticmethod
    def update_zone(zone_id: int, entry: Optional[float] = None,
                    stoploss: Optional[float] = None,
                    target: Optional[float] = None) -> Optional[Zone]:
        """Update an existing zone"""
        zone = db.session.get(Zone, zone_id)
        if zone:
            if entry is not None:
                zone.entry = entry
            if stoploss is not None:
                zone.stoploss = stoploss
            if target is not None:
                zone.target = target
            db.session.commit()
        return zone

    @staticmethod
    def delete_zone(zone_id: int) -> bool:
        """Delete a zone"""
        zone = db.session.get(Zone, zone_id)
        if zone:
            db.session.delete(zone)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_active_zones_for_ticker(ticker_id: int) -> List[Zone]:
        """Get all active zones for a specific ticker"""
        return Zone.query.filter_by(
            ticker_id=ticker_id,
        ).where(
            Zone.status.in_([ZoneStatus.ACTIVE, ZoneStatus.ENTRY_HIT])
        ).all()

    @staticmethod
    def check_zone(zone: Zone, current_price: float) -> bool:
        """
        Check if a zone has been triggered based on current price
        Returns True if zone status changed, False otherwise
        """

        now = datetime.now(timezone.utc)
        status_changed = False

        # Check for entry/failed first
        if zone.status == ZoneStatus.ACTIVE:
            if zone.type == ZoneType.LONG:
                if current_price <= zone.stoploss:
                    zone.status = ZoneStatus.FAILED
                    zone.failed_at = now
                    status_changed = True
                elif current_price <= zone.entry:
                    zone.status = ZoneStatus.ENTRY_HIT
                    zone.entry_at = now
                    status_changed = True
            else:  # SHORT zone
                if current_price >= zone.stoploss:
                    zone.status = ZoneStatus.FAILED
                    zone.failed_at = now
                    status_changed = True
                elif current_price >= zone.entry:
                    zone.status = ZoneStatus.ENTRY_HIT
                    zone.entry_at = now
                    status_changed = True

        # Check for stoploss/target after entry
        elif zone.status == ZoneStatus.ENTRY_HIT:
            if zone.type == ZoneType.LONG:
                if current_price <= zone.stoploss:
                    zone.status = ZoneStatus.STOPLOSS_HIT
                    zone.stoploss_at = now
                    status_changed = True
                elif current_price >= zone.target:
                    zone.status = ZoneStatus.TARGET_HIT
                    zone.target_at = now
                    status_changed = True
            else:  # SHORT zone
                if current_price >= zone.stoploss:
                    zone.status = ZoneStatus.STOPLOSS_HIT
                    zone.stoploss_at = now
                    status_changed = True
                elif current_price <= zone.target:
                    zone.status = ZoneStatus.TARGET_HIT
                    zone.target_at = now
                    status_changed = True

        if status_changed:
            db.session.commit()

        return status_changed