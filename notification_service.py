import requests
from app.models import *


api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY2OGUyMzBkNDA1YjU1MWM0MzcwZjdiOCIsIm5hbWUiOiJTZW5zaWJ1bGwiLCJhcHBOYW1lIjoiQWlTZW5zeSIsImNsaWVudElkIjoiNjY4ZTIzMGQ0MDViNTUxYzQzNzBmN2FjIiwiYWN0aXZlUGxhbiI6IlBST19NT05USExZIiwiaWF0IjoxNzIyNzAzMDA0fQ.ev-HcqoQ14OesvXNM1zgTRZct2onvLGS8p5DjvqdFyc"


class WhatsAppProvider:

    @classmethod
    def send(cls, destination, campaign_name, params):
        url = "https://backend.aisensy.com/campaign/t1/api/v2"

        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "apiKey": api_key,
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

    @classmethod
    def send_alert_notification(cls, user: User, alert: Alert, current_price: float) -> None:
        """Send notification for triggered alert"""

        destination = user.phone_number
        params = [alert.symbol, str(alert.price), str(current_price)]

        if alert.type == AlertType.CROSS_OVER:
            campaign_name = "alertcrossover"
        else:
            campaign_name = "alertcrossunder"

        WhatsAppProvider.send(destination, campaign_name, params)

    @classmethod
    def send_zone_notification(cls, user: User, zone: Zone) -> None:
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

        WhatsAppProvider.send(destination, campaign_name, params)