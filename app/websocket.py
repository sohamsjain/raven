from kiteconnect import KiteTicker
from datetime import datetime, timezone
import logging
from sqlalchemy import select
from app import db, create_app
from app.models import Ticker
from kite import Kite
from app.model_service import AlertManager, ZoneManager
from app.notification_service import NotificationManager


k = Kite()
app = create_app()
Notifications = NotificationManager()


# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TickerManager:
    def __init__(self):
        self.kws = None
        self.tickers = {}  # Map instrument_token to Ticker object
        self.alert_manager = AlertManager()
        self.zone_manager = ZoneManager()
        self.initialize_connection()

    def initialize_connection(self):
        """Initialize KiteTicker connection"""
        try:
            self.kws = KiteTicker(k.api_key, k.access_token)
            self.setup_handlers()
        except Exception as e:
            logger.error(f"Failed to initialize KiteTicker: {e}")
            raise

    def setup_handlers(self):
        """Set up WebSocket event handlers"""
        self.kws.on_ticks = self.on_ticks
        self.kws.on_connect = self.on_connect
        self.kws.on_close = self.on_close
        self.kws.on_error = self.on_error
        self.kws.on_reconnect = self.on_reconnect
        self.kws.on_noreconnect = self.on_noreconnect

    def load_tickers(self):
        """Load all tickers from database"""
        try:
            with app.app_context():
                stmt = select(Ticker)
                tickers = db.session.execute(stmt).scalars().all()
                self.tickers = {ticker.instrument_token: ticker for ticker in tickers}
                return list(self.tickers.keys())
        except Exception as e:
            logger.error(f"Failed to load tickers: {e}")
            raise

    def check_alerts_and_zones(self, ticker_id: int, current_price: float):
        """Check alerts and zones for a specific ticker"""
        try:
            # Check alerts
            active_alerts = self.alert_manager.get_active_alerts_for_ticker(ticker_id)
            for alert in active_alerts:
                if self.alert_manager.check_alert(alert, current_price):
                    logger.info(f"Alert triggered: {alert}")
                    Notifications.send_alert_notification(alert.user, alert, current_price)

            # Check zones
            active_zones = self.zone_manager.get_active_zones_for_ticker(ticker_id)
            for zone in active_zones:
                if self.zone_manager.check_zone(zone, current_price):
                    logger.info(f"Zone status changed: {zone}")
                    Notifications.send_zone_notification(zone.user, zone)

        except Exception as e:
            logger.error(f"Error checking alerts/zones for ticker {ticker_id}: {e}")

    def update_ticker(self, instrument_token: int, last_price: float):
        """Update ticker price and check alerts/zones"""
        try:
            with app.app_context():
                ticker = db.session.get(Ticker, self.tickers[instrument_token].id)
                if ticker:
                    ticker.last_price = last_price
                    ticker.last_updated = datetime.now(timezone.utc)

                    # Check alerts and zones before committing the price update
                    self.check_alerts_and_zones(ticker.id, last_price)

                    db.session.commit()
        except Exception as e:
            logger.error(f"Failed to update ticker {instrument_token}: {e}")
            db.session.rollback()

    def on_ticks(self, ws, ticks):
        """Callback when ticks are received"""
        for tick in ticks:
            try:
                if 'last_price' in tick:
                    print(f"{self.tickers[tick['instrument_token']].symbol}: {tick['last_price']}")
                    self.update_ticker(tick['instrument_token'], tick['last_price'])
            except Exception as e:
                logger.error(f"Error processing tick: {e}")

    def on_connect(self, ws, response):
        """Callback on successful connection"""
        logger.info("Successfully connected to WebSocket")
        instrument_tokens = self.load_tickers()
        ws.subscribe(instrument_tokens)
        ws.set_mode(ws.MODE_FULL, instrument_tokens)

    def on_close(self, ws, code, reason):
        """Callback when connection is closed"""
        logger.warning(f"Connection closed: {code} - {reason}")

    def on_error(self, ws, code, reason):
        """Callback when error occurs"""
        logger.error(f"Error in WebSocket: {code} - {reason}")

    def on_reconnect(self, ws, attempts_count):
        """Callback when reconnecting"""
        logger.info(f"Reconnecting... {attempts_count} attempt(s)")

    def on_noreconnect(self, ws):
        """Callback when reconnection fails"""
        logger.error("Maximum reconnection attempts reached")

    def start(self):
        """Start the WebSocket connection"""
        try:
            self.kws.connect(threaded=True)
        except Exception as e:
            logger.error(f"Failed to start WebSocket: {e}")
            raise

    def stop(self):
        """Stop the WebSocket connection"""
        try:
            if self.kws:
                self.kws.close()
        except Exception as e:
            logger.error(f"Error stopping WebSocket: {e}")
            raise


def main():
    ticker_manager = None
    try:
        ticker_manager = TickerManager()
        ticker_manager.start()

        # Keep the script running
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping WebSocket connection...")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        if ticker_manager:
            ticker_manager.stop()


if __name__ == "__main__":
    main()