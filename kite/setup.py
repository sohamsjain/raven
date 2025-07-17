import requests
import pyotp
import json
from os.path import join, dirname
from urllib.parse import urlparse, parse_qs
from kiteconnect.connect import KiteConnect
from kiteconnect.exceptions import TokenException
import logging

logger = logging.getLogger(__name__)


class Kite:
    default_setup_file = join(dirname(__file__), 'kite.json')

    def __init__(self, init_file=default_setup_file):
        self.init_file = init_file
        self.kite = None
        self.logged_in = False
        self.api_key = self.read_key_from_settings('api_key')
        self.api_secret = self.read_key_from_settings('api_secret')
        self.access_token = self.read_key_from_settings('access_token')
        self.user_id = self.read_key_from_settings('user_id')
        self.password = self.read_key_from_settings('password')
        self.totp_secret = self.read_key_from_settings('totp_secret')

        if self.access_token and self.api_key:
            try:
                self.kite = KiteConnect(api_key=self.api_key, access_token=self.access_token)
                self.kite.profile()
                self.logged_in = True
                logger.info("Successfully logged in with existing access token")
            except TokenException:
                logger.warning("Existing access token invalid, attempting auto-login")
                if self.auto_login():
                    logger.info("Successfully logged in with auto-login")
                    self.logged_in = True

    def auto_login(self):
        """Fully automated login using stored credentials and TOTP"""
        try:
            if not all([self.api_key, self.api_secret, self.user_id, self.password, self.totp_secret]):
                logger.error("Missing required credentials for auto-login")
                return False

            logger.info("Starting automated login process...")

            # Create session
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })

            # Step 1: Login
            login_url = "https://kite.zerodha.com/api/login"
            login_data = {
                'user_id': self.user_id,
                'password': self.password
            }

            logger.info("Submitting login credentials...")
            login_response = session.post(login_url, data=login_data)

            if login_response.status_code != 200:
                logger.error(f"Login failed with status: {login_response.status_code}")
                return False

            response_data = login_response.json()

            if response_data.get('status') != 'success':
                logger.error(f"Login failed: {response_data.get('message', 'Unknown error')}")
                return False

            # Step 2: Handle TOTP if required
            if 'request_id' in response_data.get('data', {}):
                request_id = response_data['data']['request_id']
                logger.info("TOTP required, generating code...")

                totp = pyotp.TOTP(self.totp_secret)
                totp_code = totp.now()

                totp_url = "https://kite.zerodha.com/api/twofa"
                totp_data = {
                    'request_id': request_id,
                    'twofa_value': totp_code,
                    'user_id': self.user_id
                }

                logger.info("Submitting TOTP code...")
                totp_response = session.post(totp_url, data=totp_data)

                if totp_response.status_code != 200:
                    logger.error(f"TOTP submission failed with status: {totp_response.status_code}")
                    return False

                totp_response_data = totp_response.json()

                if totp_response_data.get('status') != 'success':
                    logger.error(f"TOTP verification failed: {totp_response_data.get('message', 'Unknown error')}")
                    return False

            # Step 3: Get authorization with redirects enabled
            auth_url = f"https://kite.zerodha.com/connect/login?api_key={self.api_key}&v=3"

            logger.info("Getting authorization...")
            # This is the key fix - allow_redirects=True takes us to 127.0.0.1:3000 with request_token
            try:
                auth_response = session.get(auth_url, allow_redirects=True, timeout=3)
            except Exception as e:
                url = e.request.url

                if 'request_token=' in url:
                    parsed_url = urlparse(url)
                    query_params = parse_qs(parsed_url.query)
                    request_token = query_params.get('request_token', [None])[0]

                    if request_token:
                        logger.info(f"Request token obtained: {request_token[:10]}...")
                        return self.create_session(request_token)

                logger.error("Could not obtain request token")
                return False

        except Exception as e:
            logger.error(f"Auto-login failed: {e}")
            return False

    def create_session(self, request_token):
        """Create session with request token"""
        try:
            self.kite = KiteConnect(api_key=self.api_key)
            self.session = self.kite.generate_session(request_token=request_token, api_secret=self.api_secret)

            self.access_token = self.session['access_token']
            self.session['login_time'] = str(self.session['login_time'])

            self.write_key_to_settings('session', self.session)
            self.write_key_to_settings('access_token', self.access_token)

            self.kite.set_access_token(self.access_token)
            self.logged_in = True

            logger.info("Session created successfully")
            return True

        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            return False

    def get_login_url(self):
        """Get login URL for manual login (fallback)"""
        self.kite = KiteConnect(self.api_key)
        return self.kite.login_url()

    def ensure_login(self):
        """Ensure we are logged in, attempt auto-login if not"""
        if self.is_logged_in():
            return True

        logger.info("Not logged in, attempting auto-login...")
        return self.auto_login()

    def is_logged_in(self):
        """Check if currently logged in"""
        if not self.logged_in or not self.kite:
            return False

        try:
            self.kite.profile()
            return True
        except TokenException:
            self.logged_in = False
            return False

    def setup_credentials(self):
        """Interactive setup for storing credentials"""
        print("Setting up Kite Connect credentials...")

        if not self.api_key:
            self.api_key = input('Enter your API key: ')
            self.write_key_to_settings('api_key', self.api_key)

        if not self.api_secret:
            self.api_secret = input('Enter your API secret: ')
            self.write_key_to_settings('api_secret', self.api_secret)

        if not self.user_id:
            self.user_id = input('Enter your Zerodha user ID: ')
            self.write_key_to_settings('user_id', self.user_id)

        if not self.password:
            import getpass
            self.password = getpass.getpass('Enter your Zerodha password: ')
            self.write_key_to_settings('password', self.password)

        if not self.totp_secret:
            self.totp_secret = input('Enter your TOTP secret key: ')
            self.write_key_to_settings('totp_secret', self.totp_secret)

        if not self.read_key_from_settings('redirect_uri'):
            redirect_uri = input('Enter redirect URI (default: https://127.0.0.1:3000): ').strip()
            if not redirect_uri:
                redirect_uri = "https://127.0.0.1:3000"
            self.write_key_to_settings('redirect_uri', redirect_uri)

        print("Credentials setup complete!")

    def test_totp(self):
        """Test TOTP generation"""
        if not self.totp_secret:
            logger.error("TOTP secret not configured")
            return False

        try:
            totp = pyotp.TOTP(self.totp_secret)
            current_code = totp.now()
            logger.info(f"Current TOTP code: {current_code}")
            return True
        except Exception as e:
            logger.error(f"TOTP generation failed: {e}")
            return False

    def write_key_to_settings(self, key, value):
        """Write key-value pair to settings file"""
        try:
            try:
                with open(self.init_file, 'r') as file:
                    data = json.load(file)
            except (IOError, json.JSONDecodeError):
                data = {
                    "api_key": "", "api_secret": "", "redirect_uri": "",
                    "access_token": "", "user_id": "", "password": "",
                    "totp_secret": "", "session": {}
                }

            data[key] = value

            with open(self.init_file, 'w') as output_file:
                json.dump(data, output_file, indent=2)

        except Exception as e:
            logger.error(f"Failed to write settings: {e}")

    def read_key_from_settings(self, key):
        """Read key from settings file"""
        try:
            with open(self.init_file, 'r') as file:
                data = json.load(file)
                return data.get(key)
        except (IOError, json.JSONDecodeError):
            return None