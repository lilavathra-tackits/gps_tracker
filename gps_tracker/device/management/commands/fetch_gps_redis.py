
import requests
import redis
import json
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from datetime import datetime, timedelta, timezone as dt_timezone
from device.models import Device, DeviceData
from math import radians, sin, cos, sqrt, atan2

# Redis connection
redis_client = redis.Redis(
    host=getattr(settings, 'REDIS_HOST', 'localhost'),
    port=getattr(settings, 'REDIS_PORT', 6379),
    db=getattr(settings, 'REDIS_DB', 0),
    decode_responses=True
)

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return distance

class Command(BaseCommand):
    help = 'Fetch GPS data for all devices, process with Redis, and store in database'

    def handle(self, *args, **kwargs):
        api_url = getattr(settings, 'GPS_API_URL', 'http://127.0.0.1:8000/api/gps/')
        batch_size = getattr(settings, 'GPS_BATCH_SIZE', 100)  # Number of records to batch before DB write
        batch_data = []
        rash_threshold = 80

        while True:
            devices = Device.objects.all()
            self.stdout.write(f"Found {devices.count()} devices")
            pipeline = redis_client.pipeline()  # Use Redis pipeline for batch operations

            for device in devices:
                try:
                    # Fetch GPS data from API
                    params = {"device_id": device.device_id, "device_password": device.device_password}
                    response = requests.get(api_url, params=params, timeout=5)
                    self.stdout.write(f"Fetching data for device {device.device_id}: Status {response.status_code}")

                    if response.status_code != 200:
                        self.stdout.write(self.style.ERROR(
                            f"GPS API error for {device.device_id}: Status_EXP_{response.status_code}, Response: {response.text}"
                        ))
                        continue

                    api_data = response.json()
                    self.stdout.write(f"GPS API Response: {api_data}")

                    # Validate required fields
                    required_fields = ["device_id", "event_time", "latitude", "longitude", "Charge"]
                    missing_fields = [field for field in required_fields if field not in api_data or api_data[field] is None]
                    if missing_fields:
                        self.stdout.write(self.style.ERROR(
                            f"Invalid API response for {device.device_id}: missing fields: {', '.join(missing_fields)}"
                        ))
                        continue

                    # Parse and validate data
                    try:
                        latitude = float(api_data["latitude"])
                        longitude = float(api_data["longitude"])
                        charge = int(api_data["Charge"])
                        timestamp = str(api_data["event_time"]).strip()

                        # Parse timestamp
                        try:
                            parsed_timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                            parsed_timestamp = parsed_timestamp.replace(tzinfo=dt_timezone.utc)
                        except ValueError as e:
                            self.stdout.write(self.style.ERROR(
                                f"Invalid timestamp format for {device.device_id}: {timestamp}, Error: {str(e)}"
                            ))
                            continue

                        # Redis key for storing latest device data
                        redis_key = f"device:{device.device_id}:latest"

                        # Get previous data from Redis
                        prev_data = redis_client.get(redis_key)
                        speed = 0

                        if prev_data:
                            prev_data = json.loads(prev_data)
                            prev_timestamp = datetime.fromisoformat(prev_data["timestamp"])
                            prev_latitude = float(prev_data["latitude"])
                            prev_longitude = float(prev_data["longitude"])

                            # Calculate speed
                            distance = haversine_distance(prev_latitude, prev_longitude, latitude, longitude)
                            time_diff = (parsed_timestamp - prev_timestamp).total_seconds()
                            speed = (distance / time_diff) * 3.6 if time_diff > 0 else 0
                            self.stdout.write(f"Calculated speed for {device.device_id}: {speed} km/h")

                            # Check for rash driving
                            if speed > rash_threshold:
                                self.stdout.write(self.style.WARNING(
                                    f"Rash driving detected for {device.device_id}: Speed {speed} km/h at {parsed_timestamp}"
                                ))

                        # Store current data in Redis
                        current_data = {
                            "latitude": latitude,
                            "longitude": longitude,
                            "timestamp": parsed_timestamp.isoformat(),
                            "charge": charge
                        }
                        pipeline.set(redis_key, json.dumps(current_data), ex=3600)  # Expire after 1 hour

                        # Prepare data for batch database write
                        device_data = {
                            "device": device,
                            "latitude": latitude,
                            "longitude": longitude,
                            "altitude": 0,
                            "speed": speed,
                            "heading": 0,
                            "charge": charge,
                            "timestamp": parsed_timestamp
                        }
                        batch_data.append(device_data)
                        self.stdout.write(f"Prepared data for {device.device_id}: {parsed_timestamp.isoformat()}")

                    except (ValueError, TypeError) as e:
                        self.stdout.write(self.style.ERROR(
                            f"Data type conversion error for {device.device_id}: {str(e)}"
                        ))
                        continue
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f"Unexpected error processing data for {device.device_id}: {str(e)}"
                        ))
                        continue

                except requests.RequestException as e:
                    self.stdout.write(self.style.ERROR(
                        f"Failed to connect to GPS API for {device.device_id}: {str(e)}"
                    ))
                    continue

            # Execute Redis pipeline
            pipeline.execute()
            self.stdout.write("Redis pipeline executed")

            # Save batch to database
            if len(batch_data) >= batch_size:
                try:
                    DeviceData.objects.bulk_create([DeviceData(**data) for data in batch_data])
                    self.stdout.write(self.style.SUCCESS(f"Saved {len(batch_data)} records to database"))
                    batch_data = []  # Clear batch
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error saving batch to database: {str(e)}"))

            time.sleep(4)  # Poll every 4 seconds

            # Save any remaining batch data
            if batch_data:
                try:
                    DeviceData.objects.bulk_create([DeviceData(**data) for data in batch_data])
                    self.stdout.write(self.style.SUCCESS(f"Saved remaining {len(batch_data)} records to database"))
                    batch_data = []
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error saving remaining batch to database: {str(e)}"))