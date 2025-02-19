from kiteconnect import KiteTicker
from datetime import datetime, timezone, timedelta
import logging
import time
from sqlalchemy import select
from app import db, create_app
from app.models import Ticker
from kite import Kite
from app.model_service import AlertManager, ZoneManager
from notification_service import NotificationManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


class TickerManager:
    def __init__(self):
        self.kws = None
        self.tickers = {}  # Map instrument_token to Ticker object
        self.alert_manager = AlertManager()
        self.zone_manager = ZoneManager()
        self.app = create_app()
        self.k = None
        self.is_running = False

    def initialize_connection(self):
        """Initialize KiteTicker connection"""
        try:
            self.k = Kite()
            if not self.k.logged_in:
                logger.error("Kite not logged in")
                return False

            self.kws = KiteTicker(self.k.api_key, self.k.access_token)
            self.setup_handlers()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize KiteTicker: {e}")
            return False

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
            with self.app.app_context():
                stmt = select(Ticker)
                tickers = db.session.execute(stmt).scalars().all()
                self.tickers = {ticker.instrument_token: ticker for ticker in tickers}
                return list(self.tickers.keys())
        except Exception as e:
            logger.error(f"Failed to load tickers: {e}")
            return []

    def check_alerts_and_zones(self, ticker_id: int, current_price: float):
        """Check alerts and zones for a specific ticker"""
        try:
            # Check alerts
            active_alerts = self.alert_manager.get_active_alerts_for_ticker(ticker_id)
            for alert in active_alerts:
                if self.alert_manager.check_alert(alert, current_price):
                    logger.info(f"Alert triggered: {alert}")
                    NotificationManager.send_alert_notification(alert.user, alert, current_price)

            # Check zones
            active_zones = self.zone_manager.get_active_zones_for_ticker(ticker_id)
            for zone in active_zones:
                if self.zone_manager.check_zone(zone, current_price):
                    logger.info(f"Zone status changed: {zone}")
                    NotificationManager.send_zone_notification(zone.user, zone)

        except Exception as e:
            logger.error(f"Error checking alerts/zones for ticker {ticker_id}: {e}")

    def update_ticker(self, instrument_token: int, last_price: float):
        """Update ticker price and check alerts/zones"""
        try:
            with self.app.app_context():
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
                    logger.debug(f"{self.tickers[tick['instrument_token']].symbol}: {tick['last_price']}")
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
        self.is_running = False

    def on_error(self, ws, code, reason):
        """Callback when error occurs"""
        logger.error(f"Error in WebSocket: {code} - {reason}")
        self.is_running = False

    def on_reconnect(self, ws, attempts_count):
        """Callback when reconnecting"""
        logger.info(f"Reconnecting... {attempts_count} attempt(s)")

    def on_noreconnect(self, ws):
        """Callback when reconnection fails"""
        logger.error("Maximum reconnection attempts reached")
        self.is_running = False

    def start(self):
        """Start the WebSocket connection"""
        try:
            self.is_running = True
            self.kws.connect(threaded=True)
        except Exception as e:
            logger.error(f"Failed to start WebSocket: {e}")
            self.is_running = False

    def stop(self):
        """Stop the WebSocket connection"""
        try:
            self.is_running = False
            if self.kws:
                self.kws.close()
        except Exception as e:
            logger.error(f"Error stopping WebSocket: {e}")

    def check_market_hours(self):
        """Check if current time is within market hours (9:15 AM - 3:30 PM IST)"""
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))  # IST timezone
        if now.weekday() >= 5:  # Saturday or Sunday
            return False

        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_start <= now <= market_end

    def run_forever(self):
        """Main loop to run the ticker manager continuously"""
        while True:
            try:
                if self.check_market_hours():
                    if not self.is_running:
                        logger.info("Market hours started. Initializing connection...")
                        if self.initialize_connection():
                            self.start()
                else:
                    if self.is_running:
                        logger.info("Market hours over. Stopping connection...")
                        self.stop()
                    else:
                        next_market_time = self.get_next_market_time()
                        sleep_seconds = (next_market_time - datetime.now(
                            timezone(timedelta(hours=5, minutes=30)))).total_seconds()
                        logger.info(f"Markets closed. Sleeping until {next_market_time}")
                        time.sleep(min(sleep_seconds, 3600))  # Sleep until next market day or max 1 hour
                        continue

                time.sleep(1)  # Check every second during market hours

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                if self.is_running:
                    self.stop()
                time.sleep(60)  # Wait before retrying

    def get_next_market_time(self):
        """Calculate the next market opening time"""
        now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        next_day = now + timedelta(days=1)

        while True:
            if next_day.weekday() < 5:  # Monday to Friday
                return next_day.replace(hour=9, minute=15, second=0, microsecond=0)
            next_day += timedelta(days=1)


def main():
    logger.info("Starting Raven WebSocket Manager")
    manager = TickerManager()
    manager.run_forever()


if __name__ == "__main__":
    main()