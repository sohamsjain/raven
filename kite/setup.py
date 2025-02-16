from kiteconnect.connect import *
from kiteconnect.exceptions import *
import json
from os.path import join, dirname


setup_file_path = join(dirname(__file__), 'kite.json')


class Kite:
    default_setup_file = setup_file_path
    exchanges = []

    def __init__(self, init_file=default_setup_file):
        self.init_file = init_file
        self.equity_margin = 0
        self.commodity_margin = 0
        self.kite = None
        self.logged_in = False
        self.api_key = self.read_key_from_settings('api_key')
        self.access_token = self.read_key_from_settings('access_token')
        self.session = self.read_key_from_settings('session')
        if self.access_token is not None and self.api_key is not None:
            try:
                self.kite = KiteConnect(api_key=self.api_key, access_token=self.access_token)
                self.kite.profile()
                self.logged_in = True
            except TokenException as te:
                print('Token Exception: [%s]. \nRegenerating Session\n\n' % te)

        if self.logged_in is False:
            self.api_key = self.read_key_from_settings('api_key')
            if self.api_key is None:
                self.api_key = input('What is your app''s API key:  ')
                self.write_key_to_settings('api_key', self.api_key)

            self.api_secret = self.read_key_from_settings('api_secret')
            if self.api_secret is None:
                self.api_secret = input('What is your app''s API secret:  ')
                self.write_key_to_settings('api_secret', self.api_secret)

            self.redirect_uri = self.read_key_from_settings('redirect_uri')
            if self.redirect_uri is None:
                self.redirect_uri = input('What is your app''s redirect_uri:  ')
                self.write_key_to_settings('redirect_uri', self.redirect_uri)

            self.username = self.read_key_from_settings('username')
            if self.username is None:
                self.username = input('What is your account''s username:  ')
                self.write_key_to_settings('username', self.username)

            self.password = self.read_key_from_settings('password')
            if self.password is None:
                self.password = input('What is your account''s password:  ')
                self.write_key_to_settings('password', self.password)

            self.pin = self.read_key_from_settings('pin')
            if self.pin is None:
                self.pin = input('What is your account''s pin:  ')
                self.write_key_to_settings('pin', self.pin)

            self.kite = KiteConnect(self.api_key)
            self.url = self.kite.login_url()

            print(self.url)
            request_token = input("Request Token: ")
            self.session = self.kite.generate_session(request_token=request_token, api_secret=self.api_secret)

            try:
                self.access_token = self.session['access_token']
            except SystemError as se:
                print('Uh oh, there seems to be something wrong. Error: [%s]' % se)
                return

            self.session['login_time'] = str(self.session['login_time'])
            self.write_key_to_settings('session', self.session)
            self.write_key_to_settings('access_token', self.access_token)
            self.kite.set_access_token(self.access_token)

    def write_key_to_settings(self, key, value):
        try:
            file = open(self.init_file, 'r')
        except IOError:
            data = {"api_key": "", "api_secret": "", "redirect_uri": "", "access_token": "", "username": "",
                    "password": "", "pin": ""}
            with open(self.init_file, 'w') as output_file:
                json.dump(data, output_file)
        file = open(self.init_file, 'r')
        try:
            data = json.load(file)
        except Exception:
            data = {}
        data[key] = value
        with open(self.init_file, 'w') as output_file:
            json.dump(data, output_file)

    def read_key_from_settings(self, key):
        try:
            file = open(self.init_file, 'r')
        except IOError:
            file = open(self.init_file, 'w')
        file = open(self.init_file, 'r')
        try:
            data = json.load(file)
            return data[key]
        except Exception:
            pass
        return None


if __name__ == '__main__':
    k = Kite()