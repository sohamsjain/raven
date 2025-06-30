from kiteconnect import KiteTicker
from datetime import datetime, timezone, timedelta
import logging
import time
from collections import defaultdict, deque
from sqlalchemy import select
from app import db, create_app
from app.models import Ticker, User
from kite import Kite
from app.model_service import AlertManager, ZoneManager
from notification_service import NotificationManager
import threading
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# IST timezone
IST = pytz.timezone('Asia/Kolkata')


class CandleData:
    """Represents a 5-second candle"""

    def __init__(self, timestamp, open_price):
        self.timestamp = timestamp
        self.open = open_price
        self.high = open_price
        self.low = open_price
        self.close = open_price
        self.volume = 0
        self.tick_count = 0

    def update_tick(self, price, volume=0):
        """Update candle with new tick data"""
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume
        self.tick_count += 1

    def is_complete(self, current_time):
        """Check if this 5-second candle is complete"""
        return (current_time - self.timestamp).total_seconds() >= 5

    def __repr__(self):
        return f"Candle(O:{self.open} H:{self.high} L:{self.low} C:{self.close} V:{self.volume})"


class TickerManager:
    def __init__(self):
        self.kws = None
        self.tickers = {}  # Map instrument_token to Ticker object
        self.alert_manager = AlertManager()
        self.zone_manager = ZoneManager()
        self.app = create_app()
        self.k = None
        self.is_running = False

        # Candle data storage: {instrument_token: current_candle}
        self.current_candles = {}
        # Store recent candles for each instrument: {instrument_token: deque of recent candles}
        self.candle_history = defaultdict(lambda: deque(maxlen=20))  # Keep last 20 candles

        # Lock for thread safety
        self.data_lock = threading.Lock()

        # Timer for processing candles
        self.candle_timer = None

    def initialize_connection(self):
        """Initialize KiteTicker connection"""
        try:
            del self.k
            self.k = Kite()
            if not self.k.logged_in:
                logger.error("Kite not logged in")
                with self.app.app_context():
                    admins = User.query.where(User.is_admin==True).all()
                    for admin in admins:
                        NotificationManager.send_kite_login_alert(admin)
                return False

            self.kws = KiteTicker(self.k.api_key, self.k.access_token)
            self.setup_handlers()
            self.start_candle_processor()
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

    def start_candle_processor(self):
        """Start the candle processing timer"""
        self.process_completed_candles()
        # Schedule next processing in 1 second
        self.candle_timer = threading.Timer(1.0, self.start_candle_processor)
        self.candle_timer.start()

    def stop_candle_processor(self):
        """Stop the candle processing timer"""
        if self.candle_timer:
            self.candle_timer.cancel()

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

    def is_trading_hours(self, tick_time):
        """Check if the tick time falls within regular trading hours (9:15 AM - 3:30 PM IST)"""
        tick_time_ist = tick_time.astimezone(IST)

        # Check if it's a weekday (Monday=0, Sunday=6)
        if tick_time_ist.weekday() >= 5:  # Saturday or Sunday
            return False

        # Define trading hours in IST
        market_start = tick_time_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = tick_time_ist.replace(hour=15, minute=30, second=0, microsecond=0)

        return market_start <= tick_time_ist <= market_end

    def get_candle_timestamp(self, timestamp):
        """Get the 5-second candle timestamp (floor to nearest 5-second interval) in IST"""
        # Convert to IST if needed
        if timestamp.tzinfo is None:
            timestamp_ist = IST.localize(timestamp)
        else:
            timestamp_ist = timestamp.astimezone(IST)

        seconds = timestamp_ist.second
        floored_seconds = (seconds // 5) * 5
        return timestamp_ist.replace(second=floored_seconds, microsecond=0)

    def process_tick(self, instrument_token, price, volume=0, timestamp=None):
        """Process individual tick and update candle data"""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        candle_timestamp = self.get_candle_timestamp(timestamp)

        with self.data_lock:
            # Check if we need to create a new candle
            if (instrument_token not in self.current_candles or
                    self.current_candles[instrument_token].timestamp != candle_timestamp):

                # Save previous candle if it exists
                if instrument_token in self.current_candles:
                    prev_candle = self.current_candles[instrument_token]
                    self.candle_history[instrument_token].append(prev_candle)
                    logger.debug(f"Completed candle for {self.tickers[instrument_token].symbol}: {prev_candle}")

                # Create new candle
                self.current_candles[instrument_token] = CandleData(candle_timestamp, price)
                logger.debug(f"Started new candle for {self.tickers[instrument_token].symbol} at {candle_timestamp}")

            # Update current candle with tick data
            self.current_candles[instrument_token].update_tick(price, volume)

    def process_completed_candles(self):
        """Process all completed 5-second candles and check alerts/zones"""
        current_time = datetime.now(IST)
        completed_instruments = []

        with self.data_lock:
            # Find all completed candles
            for instrument_token, candle in self.current_candles.items():
                if candle.is_complete(current_time):
                    completed_instruments.append((instrument_token, candle))

        # Process completed candles outside the lock
        for instrument_token, candle in completed_instruments:
            try:
                ticker = self.tickers[instrument_token]

                # Update ticker price in database
                self.update_ticker_price(ticker, candle.close, current_time)

                # Check alerts and zones using candle close price
                self.check_alerts_and_zones(ticker.id, candle.close, candle)

                # Move completed candle to history
                with self.data_lock:
                    if instrument_token in self.current_candles:
                        self.candle_history[instrument_token].append(candle)
                        del self.current_candles[instrument_token]

                logger.debug(f"Processed completed candle for {ticker.symbol}: {candle}")

            except Exception as e:
                logger.error(f"Error processing completed candle for {instrument_token}: {e}")

    def update_ticker_price(self, ticker, price, timestamp):
        """Update ticker price in database"""
        try:
            with self.app.app_context():
                db_ticker = db.session.get(Ticker, ticker.id)
                if db_ticker:
                    db_ticker.last_price = price
                    db_ticker.last_updated = timestamp
                    db.session.commit()
        except Exception as e:
            logger.error(f"Failed to update ticker {ticker.symbol}: {e}")
            with self.app.app_context():
                db.session.rollback()

    def check_alerts_and_zones(self, ticker_id: int, current_price: float, candle: CandleData):
        """Check alerts and zones for a specific ticker using candle data"""
        try:
            with self.app.app_context():
                # Check alerts using candle data for more accurate triggering
                active_alerts = self.alert_manager.get_active_alerts_for_ticker(ticker_id)
                for alert in active_alerts:
                    alert_triggered = self.check_alert_with_candle(alert, candle)
                    if alert_triggered:
                        logger.info(f"Alert triggered: {alert} at price {current_price} (Candle: {candle})")
                        NotificationManager.send_alert_notification(alert.user, alert, current_price)

                # Check zones using candle data (we can use high/low for more accurate zone checking)
                active_zones = self.zone_manager.get_active_zones_for_ticker(ticker_id)
                for zone in active_zones:
                    # Check zone using candle high/low for more accurate detection
                    zone_triggered = self.check_zone_with_candle(zone, candle)
                    if zone_triggered:
                        logger.info(f"Zone status changed: {zone} (Candle: {candle})")
                        NotificationManager.send_zone_notification(zone.user, zone)

        except Exception as e:
            logger.error(f"Error checking alerts/zones for ticker {ticker_id}: {e}")

    def check_alert_with_candle(self, alert, candle: CandleData) -> bool:
        """Simple alert checking using candle high/low data"""
        from app.models import AlertType, AlertStatus

        if alert.status != AlertStatus.ACTIVE:
            return False

        triggered = False

        if alert.type == AlertType.CROSS_OVER:
            # Cross Over: Check if candle high reached or exceeded alert price
            triggered = candle.high >= alert.price

        elif alert.type == AlertType.CROSS_UNDER:
            # Cross Under: Check if candle low reached or went below alert price
            triggered = candle.low <= alert.price

        if triggered:
            alert.status = AlertStatus.TRIGGERED
            alert.triggered_at = datetime.now(IST)
            db.session.commit()

        return triggered

    def check_zone_with_candle(self, zone, candle: CandleData) -> bool:
        """Enhanced zone checking using candle high/low data"""
        from app.models import ZoneType, ZoneStatus

        now = datetime.now(IST)
        status_changed = False

        # For more accurate zone detection, check if candle high/low touched the levels
        candle_high = candle.high
        candle_low = candle.low
        candle_close = candle.close

        # Check for entry/failed first
        if zone.status == ZoneStatus.ACTIVE:
            if zone.type == ZoneType.LONG:
                # Long zone: entry when price dips to entry level, failed if it goes below stoploss
                if candle_low <= zone.stoploss:
                    zone.status = ZoneStatus.FAILED
                    zone.failed_at = now
                    status_changed = True
                elif candle_low <= zone.entry:
                    zone.status = ZoneStatus.ENTRY_HIT
                    zone.entry_at = now
                    status_changed = True
            else:  # SHORT zone
                # Short zone: entry when price rises to entry level, failed if it goes above stoploss
                if candle_high >= zone.stoploss:
                    zone.status = ZoneStatus.FAILED
                    zone.failed_at = now
                    status_changed = True
                elif candle_high >= zone.entry:
                    zone.status = ZoneStatus.ENTRY_HIT
                    zone.entry_at = now
                    status_changed = True

        # Check for stoploss/target after entry
        elif zone.status == ZoneStatus.ENTRY_HIT:
            if zone.type == ZoneType.LONG:
                if candle_low <= zone.stoploss:
                    zone.status = ZoneStatus.STOPLOSS_HIT
                    zone.stoploss_at = now
                    status_changed = True
                elif candle_high >= zone.target:
                    zone.status = ZoneStatus.TARGET_HIT
                    zone.target_at = now
                    status_changed = True
            else:  # SHORT zone
                if candle_high >= zone.stoploss:
                    zone.status = ZoneStatus.STOPLOSS_HIT
                    zone.stoploss_at = now
                    status_changed = True
                elif candle_low <= zone.target:
                    zone.status = ZoneStatus.TARGET_HIT
                    zone.target_at = now
                    status_changed = True

        if status_changed:
            db.session.commit()

        return status_changed

    def on_ticks(self, ws, ticks):
        """Callback when ticks are received"""
        for tick in ticks:
            try:
                if 'last_price' in tick and 'last_trade_time' in tick and tick['instrument_token'] in self.tickers:
                    # Check if tick is within trading hours
                    last_trade_time = tick['last_trade_time']
                    if not self.is_trading_hours(last_trade_time):
                        logger.debug(f"Skipping tick outside trading hours: {last_trade_time}")
                        continue

                    # Extract tick data
                    instrument_token = tick['instrument_token']
                    price = tick['last_price']
                    volume = tick.get('volume', 0)

                    # Process tick into candle data using last_trade_time
                    self.process_tick(instrument_token, price, volume, last_trade_time)

                    # Log every 100th tick to avoid spam
                    current_candle = self.current_candles.get(instrument_token)
                    if current_candle and current_candle.tick_count % 100 == 0:
                        logger.debug(
                            f"{self.tickers[instrument_token].symbol}: Price={price}, Time={last_trade_time}, Candle={current_candle}")

            except Exception as e:
                logger.error(f"Error processing tick: {e}")

    def on_connect(self, ws, response):
        """Callback on successful connection"""
        logger.info("Successfully connected to WebSocket")
        instrument_tokens = self.load_tickers()
        if instrument_tokens:
            ws.subscribe(instrument_tokens)
            ws.set_mode(ws.MODE_FULL, instrument_tokens)
            logger.info(f"Subscribed to {len(instrument_tokens)} instruments")
        else:
            logger.warning("No instruments to subscribe to")

    def on_close(self, ws, code, reason):
        """Callback when connection is closed"""
        logger.warning(f"Connection closed: {code} - {reason}")
        self.is_running = False
        self.stop_candle_processor()

    def on_error(self, ws, code, reason):
        """Callback when error occurs"""
        logger.error(f"Error in WebSocket: {code} - {reason}")
        self.is_running = False
        self.stop_candle_processor()

    def on_reconnect(self, ws, attempts_count):
        """Callback when reconnecting"""
        logger.info(f"Reconnecting... {attempts_count} attempt(s)")

    def on_noreconnect(self, ws):
        """Callback when reconnection fails"""
        logger.error("Maximum reconnection attempts reached")
        self.is_running = False
        self.stop_candle_processor()

    def start(self):
        """Start the WebSocket connection"""
        try:
            self.is_running = True
            self.kws.connect(threaded=True)
            logger.info("WebSocket connection started")
        except Exception as e:
            logger.error(f"Failed to start WebSocket: {e}")
            self.is_running = False

    def stop(self):
        """Stop the WebSocket connection"""
        try:
            self.is_running = False
            self.stop_candle_processor()
            if self.kws:
                self.kws.close()
            logger.info("WebSocket connection stopped")
        except Exception as e:
            logger.error(f"Error stopping WebSocket: {e}")

    def check_market_hours(self):
        """Check if current time is within market hours (9:15 AM - 3:30 PM IST)"""
        now = datetime.now(IST)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False

        market_start = now.replace(hour=8, minute=15, second=0, microsecond=0)
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
                            logger.error("Failed to initialize connection. Retrying in 30 seconds...")
                            time.sleep(30)
                            continue
                else:
                    if self.is_running:
                        logger.info("Market hours over. Stopping connection...")
                        self.stop()
                    else:
                        next_market_time = self.get_next_market_time()
                        sleep_seconds = (next_market_time - datetime.now(IST)).total_seconds()
                        logger.info(f"Markets closed. Sleeping until {next_market_time}")
                        time.sleep(min(sleep_seconds, 3600))  # Sleep until next market day or max 1 hour
                        continue

                time.sleep(5)  # Check every 5 seconds during market hours

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                if self.is_running:
                    self.stop()
                time.sleep(60)  # Wait before retrying

    def get_next_market_time(self):
        """Calculate the next market opening time"""
        now = datetime.now(IST)
        market_start = now.replace(hour=8, minute=15, second=0, microsecond=0)
        next_day = now + timedelta(days=1) if now > market_start else now

        while True:
            if next_day.weekday() < 5:  # Monday to Friday
                return next_day.replace(hour=8, minute=15, second=0, microsecond=0)
            next_day += timedelta(days=1)

    def get_candle_stats(self):
        """Get statistics about current candles (for debugging)"""
        with self.data_lock:
            stats = {}
            current_time = datetime.now(IST)
            for instrument_token, candle in self.current_candles.items():
                ticker = self.tickers[instrument_token]
                stats[ticker.symbol] = {
                    'ticks': candle.tick_count,
                    'candle': str(candle),
                    'age_seconds': (current_time - candle.timestamp).total_seconds()
                }
            return stats


def main():
    logger.info("Starting Raven WebSocket Manager with 5-second candle resampling")
    manager = TickerManager()

    # Add a debug timer to print stats every 30 seconds
    def print_stats():
        if manager.is_running:
            stats = manager.get_candle_stats()
            if stats:
                logger.info(f"Current candle stats: {len(stats)} active candles")
                for symbol, data in list(stats.items())[:3]:  # Show first 3
                    logger.debug(f"{symbol}: {data}")

        # Schedule next stats print
        if manager.is_running:
            threading.Timer(30.0, print_stats).start()

    # Start stats printing
    threading.Timer(30.0, print_stats).start()

    # Run the main loop
    manager.run_forever()


if __name__ == "__main__":
    main()
