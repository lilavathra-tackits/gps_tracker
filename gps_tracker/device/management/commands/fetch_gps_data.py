import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from device.models import Device, DeviceData
from .utils import haversine_distance, parse_timestamp, calculate_speed, calculate_heading
from datetime import timedelta
import time

class Command(BaseCommand):
    help = 'Fetch GPS data for all devices and store in database'

    def handle(self, *args, **kwargs):
        api_url = getattr(settings, 'GPS_API_URL', 'http://127.0.0.1:8000/api/gps/')
        while True:
            devices = Device.objects.all()
            self.stdout.write(f"Found {devices.count()} devices")
            for device in devices:
                try:
                    params = {"device_id": device.device_id, "device_password": device.device_password}
                    response = requests.get(api_url, params=params, timeout=5)
                    self.stdout.write(f"Fetching data for device {device.device_id}: Status {response.status_code}")
                    if response.status_code != 200:
                        self.stdout.write(self.style.ERROR(
                            f"GPS API error for {device.device_id}: Status {response.status_code}, Response: {response.text}"
                        ))
                        continue
                    api_data = response.json()
                    self.stdout.write(f"GPS API Response: {api_data}")
                    required_fields = ["device_id", "event_time", "latitude", "longitude", "Charge"]
                    missing_fields = [field for field in required_fields if field not in api_data or api_data[field] is None]
                    if missing_fields:
                        self.stdout.write(self.style.ERROR(
                            f"Invalid API response for {device.device_id}: missing fields: {', '.join(missing_fields)}"
                        ))
                        continue
                    try:
                        latitude = float(api_data["latitude"])
                        longitude = float(api_data["longitude"])
                        charge = int(api_data["Charge"])
                        parsed_timestamp = parse_timestamp(api_data["event_time"])
                        if not parsed_timestamp or parsed_timestamp.tzinfo is None:
                            self.stdout.write(self.style.ERROR(
                                f"Invalid or naive timestamp for {device.device_id}: raw event_time='{api_data['event_time']}', parsed={parsed_timestamp}"
                            ))
                            continue
                        latest_data = DeviceData.objects.filter(device=device).order_by('-timestamp').first()
                        if latest_data and latest_data.timestamp == parsed_timestamp:
                            parsed_timestamp += timedelta(microseconds=1)
                            self.stdout.write(f"Adjusted timestamp to avoid duplicate: {parsed_timestamp}")
                        current_point = type('Data', (), {
                            'latitude': latitude,
                            'longitude': longitude,
                            'timestamp': parsed_timestamp
                        })()
                        speed = calculate_speed(current_point, latest_data)
                        if not latest_data:
                            self.stdout.write(f"No previous data for {device.device_id}, setting heading to 0")
                            heading = 0
                        else:
                            heading = calculate_heading(current_point, latest_data)
                        rash_threshold = 80
                        if speed > rash_threshold:
                            self.stdout.write(self.style.WARNING(
                                f"Rash driving detected for {device.device_id}: Speed {speed} km/h at {parsed_timestamp}"
                            ))
                        device_data = DeviceData(
                            device=device,
                            latitude=latitude,
                            longitude=longitude,
                            altitude=0,
                            speed=speed,
                            heading=heading,
                            charge=charge,
                            timestamp=parsed_timestamp
                        )
                        device_data.save()
                        self.stdout.write(self.style.SUCCESS(
                            f"Saved data for {device.device_id}: {parsed_timestamp.isoformat()}, Speed: {speed:.2f} km/h, Heading: {heading:.2f}°"
                        ))
                    except (ValueError, TypeError) as e:
                        self.stdout.write(self.style.ERROR(
                            f"Data type conversion error for {device.device_id}: {str(e)}"
                        ))
                        continue
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f"Unexpected error saving data for {device.device_id}: {str(e)}"
                        ))
                        continue
                except requests.RequestException as e:
                    self.stdout.write(self.style.ERROR(
                        f"Failed to connect to GPS API for {device.device_id}: {str(e)}"
                    ))
            time.sleep(4)  # Poll every 4 seconds