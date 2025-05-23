import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from device.models import Device, DeviceData
from device.utils import parse_timestamp, process_device_data
import time
import logging
import math

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fetch GPS data for all devices and store in database'

    def handle(self, *args, **kwargs):
        api_url = getattr(settings, 'GPS_API_URL', 'http://127.0.0.1:8000/api/gps/')
        while True:
            devices = Device.objects.all()
            self.stdout.write(f"Found {devices.count()} devices")
            for device in devices:
                try:
                    latest_data = DeviceData.objects.filter(device=device).order_by('-timestamp').first()
                    polling_interval = 4
                    if latest_data and latest_data.power_source == 'battery':
                        polling_interval = device.update_interval * 60
                        if latest_data.timestamp:
                            time_since_last_update = (timezone.now() - latest_data.timestamp).total_seconds()
                            if time_since_last_update < polling_interval:
                                self.stdout.write(f"Skipping {device.device_id}: Next update in {polling_interval - time_since_last_update:.0f} seconds")
                                continue

                    params = {"device_id": device.device_id, "device_password": device.device_password}
                    response = requests.get(api_url, params=params, timeout=5)
                    self.stdout.write(f"Fetching data for device {device.device_id}: Status {response.status_code}")
                    if response.status_code != 200:
                        logger.error(f"GPS API error for {device.device_id}: Status {response.status_code}, Response: {response.text}")
                        continue

                    api_data = response.json()
                    required_fields = ["device_id", "event_time", "latitude", "longitude", "Charge", "power_source"]
                    missing_fields = [field for field in required_fields if field not in api_data or api_data[field] is None]
                    if missing_fields:
                        logger.error(f"Invalid API response for {device.device_id}: missing fields: {', '.join(missing_fields)}")
                    try:
                        latitude = float(api_data["latitude"])
                        longitude = float(api_data["longitude"])
                        charge = int(api_data["Charge"])
                        power_source = api_data["power_source"]
                        parsed_timestamp = parse_timestamp(api_data["event_time"])
                        if not parsed_timestamp or parsed_timestamp.tzinfo is None:
                            logger.error(f"Invalid or naive timestamp for {device.device_id}: raw event_time='{api_data['event_time']}', parsed={parsed_timestamp}")
                            continue

                        process_device_data(
                            device=device,
                            latitude=latitude,
                            longitude=longitude,
                            altitude=float(api_data.get("altitude", 0)),
                            charge=charge,
                            timestamp=parsed_timestamp,
                            power_source=power_source
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f"Saved data for {device.device_id}: {parsed_timestamp.isoformat()}"
                        ))
                    except (ValueError, TypeError) as e:
                        logger.error(f"Data type conversion error for {device.device_id}: {str(e)}")
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected error saving data for {device.device_id}: {str(e)}")
                        continue
                except requests.RequestException as e:
                    logger.error(f"Failed to connect to GPS API for {device.device_id}: {str(e)}")
                    continue

            min_interval = min((device.update_interval * 60 for device in Device.objects.all()), default=4)
            self.stdout.write(f"Sleeping for {min_interval} seconds")
            time.sleep(min_interval)
            
            
"""
Install dependencies from requirement.txt
When setting up the project on a new system, install all dependencies using:

pip install -r requirements.txt
"""