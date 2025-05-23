from datetime import timedelta
from django.utils import timezone
from device.models import DeviceData, SpeedAlert, Notification, MaintenanceRecord
from math import radians, sin, cos, sqrt, atan2, degrees

def parse_timestamp(timestamp_str):
    try:
        return timezone.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in km
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def calculate_total_distance(data_points):
    if not data_points or data_points.count() < 2:
        return 0
    total = 0
    points = list(data_points)
    for i in range(len(points) - 1):
        total += haversine_distance(
            points[i].latitude, points[i].longitude,
            points[i+1].latitude, points[i+1].longitude
        )
    return total * 1000  # Convert to meters

def calculate_speed(current_data, previous_data):
    if not previous_data:
        return 0
    distance = haversine_distance(
        previous_data.latitude, previous_data.longitude,
        current_data.latitude, current_data.longitude
    )
    time_diff = (current_data.timestamp - previous_data.timestamp).total_seconds() / 3600
    return (distance / time_diff) if time_diff > 0 else 0

def calculate_heading(current_data, previous_data):
    if not previous_data:
        return 0
    lat1, lon1 = radians(previous_data.latitude), radians(previous_data.longitude)
    lat2, lon2 = radians(current_data.latitude), radians(current_data.longitude)
    dlon = lon2 - lon1
    y = sin(dlon) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    heading = atan2(y, x)
    heading = (degrees(heading) + 360) % 360
    return heading

def process_device_data(device, latitude, longitude, altitude, charge, timestamp, power_source, speed=0, heading=0):
    latest_data = DeviceData.objects.filter(device=device).order_by('-timestamp').first()
    
    current_point = type('Data', (), {'latitude': latitude, 'longitude': longitude, 'timestamp': timestamp})()
    speed = calculate_speed(current_point, latest_data) if latest_data and speed == 0 else speed
    heading = calculate_heading(current_point, latest_data) if latest_data and heading == 0 else heading

    if latest_data and latest_data.timestamp == timestamp:
        timestamp += timedelta(microseconds=1)
    device_data = DeviceData(
        device=device,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        speed=speed,
        heading=heading,
        charge=charge,
        timestamp=timestamp,
        power_source=power_source
    )
    device_data.save()

    if latest_data:
        distance = haversine_distance(latest_data.latitude, latest_data.longitude, latitude, longitude)
        if distance > 0.5:
            Notification.objects.create(
                device=device,
                user=device.user,
                message=f"Device moved significantly: Primary ({latest_data.latitude}, {latest_data.longitude}) to Secondary ({latitude}, {longitude})",
                timestamp=timezone.now()
            )

    if speed > 50:
        SpeedAlert.objects.create(
            device=device,
            message="Speed exceeded 50 km/h",
            speed=speed,
            timestamp=timestamp
        )
    if latest_data and latest_data.speed > 0:
        speed_diff = speed - latest_data.speed
        time_diff = (timestamp - latest_data.timestamp).total_seconds() / 3600
        if time_diff > 0:
            accel = speed_diff / time_diff
            if accel > 100 or accel < -100:
                SpeedAlert.objects.create(
                    device=device,
                    message=f"Abnormal speed {'increase' if accel > 0 else 'decrease'}",
                    speed=speed,
                    timestamp=timestamp
                )

    if speed == 0 and latest_data:
        stationary_time = (timestamp - latest_data.timestamp).total_seconds() / 60
        if stationary_time >= 10:
            status = 'off' if power_source == 'battery' else 'sleep'
            Notification.objects.create(
                device=device,
                user=device.user,
                message=f"Device in {status} mode: Stationary for {stationary_time:.1f} minutes",
                timestamp=timezone.now()
            )

    total_distance = calculate_total_distance(DeviceData.objects.filter(device=device))
    last_maintenance = MaintenanceRecord.objects.filter(device=device).order_by('-timestamp').first()
    if not last_maintenance or (timezone.now() - last_maintenance.timestamp).days > 30 or total_distance / 1000 > 1000:
        MaintenanceRecord.objects.create(
            device=device,
            status="Maintenance required",
            timestamp=timezone.now()
        )
        Notification.objects.create(
            device=device,
            user=device.user,
            message="Device requires maintenance",
            timestamp=timezone.now()
        )

    return device_data