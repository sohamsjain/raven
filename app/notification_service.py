import requests
from app.models import *


class WhatsAppProvider:
    def __init__(self):
        self.api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY2OGUyMzBkNDA1YjU1MWM0MzcwZjdiOCIsIm5hbWUiOiJTZW5zaWJ1bGwiLCJhcHBOYW1lIjoiQWlTZW5zeSIsImNsaWVudElkIjoiNjY4ZTIzMGQ0MDViNTUxYzQzNzBmN2FjIiwiYWN0aXZlUGxhbiI6IlBST19NT05USExZIiwiaWF0IjoxNzIyNzAzMDA0fQ.ev-HcqoQ14OesvXNM1zgTRZct2onvLGS8p5DjvqdFyc"

    def send(self, destination, campaign_name, params):
        url = "https://backend.aisensy.com/campaign/t1/api/v2"

        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "apiKey": self.api_key,
            "campaignName": campaign_name,
            "destination": destination,
            "userName": "Sensibull",
            "templateParams": params,
            "source": "new-landing-page form",
            "media": {},
            "buttons": [],
            "carouselCards": [],
            "location": {},
            "paramsFallbackValue": {
                "FirstName": "User"
            }
        }

        response = requests.post(url, headers=headers, json=payload)
        return response


class NotificationManager:
    def __init__(self):
        self.whatsapp_provider = WhatsAppProvider()

    def send_alert_notification(self, user: User, alert: Alert, current_price: float) -> None:
        """Send notification for triggered alert"""

        destination = user.phone_number
        params = [alert.symbol, str(alert.price), str(current_price)]

        if alert.type == AlertType.CROSS_OVER:
            campaign_name = "alertcrossover"
        else:
            campaign_name = "alertcrossunder"

        self.whatsapp_provider.send(destination, campaign_name, params)

    def send_zone_notification(self, user: User, zone: Zone) -> None:
        """Send notification for zone events"""

        destination = user.phone_number
        params = [zone.symbol, str(zone.entry), str(zone.stoploss), str(zone.target)]

        if zone.type == ZoneType.LONG:
            if zone.status == ZoneStatus.ENTRY_HIT:
                campaign_name = "entrylong"
            elif zone.status == ZoneStatus.FAILED:
                campaign_name = "failedlong"
            elif zone.status == ZoneStatus.STOPLOSS_HIT:
                campaign_name = "stoplong"
            elif zone.status == ZoneStatus.TARGET_HIT:
                campaign_name = "targetlong"

        else:
            if zone.status == ZoneStatus.ENTRY_HIT:
                campaign_name = "entryshort"
            elif zone.status == ZoneStatus.FAILED:
                campaign_name = "failedshort"
            elif zone.status == ZoneStatus.STOPLOSS_HIT:
                campaign_name = "stopshort"
            elif zone.status == ZoneStatus.TARGET_HIT:
                campaign_name = "targetshort"

        self.whatsapp_provider.send(destination, campaign_name, params)