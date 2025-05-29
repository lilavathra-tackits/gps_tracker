from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Device, DeviceData, SpeedAlert, DeviceShare, Notification, MaintenanceRecord
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from django.db import IntegrityError
from django.views.decorators.csrf import csrf_protect
import json
from .utils import parse_timestamp, calculate_total_distance, calculate_speed
from django.db.models import Sum, Avg, Max, Min, Count
from math import radians, sin, cos, sqrt, atan2
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash


@login_required
def home(request):
    # Devices linked and active
    devices = Device.objects.filter(user=request.user)
    shared_devices = DeviceShare.objects.filter(shared_with=request.user)
    total_devices = devices.count() + shared_devices.count()
    
    # Active devices: Devices with data in the last 10 minutes
    ten_minutes_ago = timezone.now() - timedelta(minutes=10)
    active_devices = Device.objects.filter(
        devicedata__timestamp__gte=ten_minutes_ago
    ).filter(user=request.user).distinct().count() + DeviceShare.objects.filter(
        shared_with=request.user,
        device__devicedata__timestamp__gte=ten_minutes_ago
    ).distinct().count()
    
    # All notifications for the user (across all devices)
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    
    # Combine owned and shared devices for display
    all_devices = []
    for device in devices:
        latest_data = DeviceData.objects.filter(device=device).order_by('-timestamp').first()
        all_devices.append({
            'device': device,
            'is_shared': False,
            'status': 'Active' if latest_data and (timezone.now() - latest_data.timestamp).total_seconds() / 60 < 10 else 'Inactive',
        })
    for share in shared_devices:
        latest_data = DeviceData.objects.filter(device=share.device).order_by('-timestamp').first()
        all_devices.append({
            'device': share.device,
            'is_shared': True,
            'status': 'Active' if latest_data and (timezone.now() - latest_data.timestamp).total_seconds() / 60 < 10 else 'Inactive',
        })
    
    return render(request, 'device/home.html', {
        'total_devices': total_devices,
        'active_devices': active_devices,
        'all_devices': all_devices,
        'notifications': notifications,
    })

@login_required
def device_list(request):
    devices = Device.objects.filter(user=request.user)
    shared_devices = DeviceShare.objects.filter(shared_with=request.user)
    # All notifications for the user (across all devices)
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    return render(request, 'device/device_list.html', 
                  {'devices': devices, 
                   'shared_devices': shared_devices, 
                   'notifications':notifications})

@login_required
def add_device(request):
    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        alias = request.POST.get('alias')
        device_password = request.POST.get('device_password')
        update_interval = request.POST.get('update_interval', 60)
        
        if not device_id or not device_password:
            messages.error(request, 'Device ID and password are required.')
            return render(request, 'device/add_device.html')
        
        if Device.objects.filter(device_id=device_id).exists():
            messages.error(request, 'Device ID already exists.')
            return render(request, 'device/add_device.html')
        
        try:
            update_interval = int(update_interval)
            if update_interval < 1:
                raise ValueError
        except ValueError:
            messages.error(request, 'Invalid update interval.')
            return render(request, 'device/add_device.html')
        
        Device.objects.create(
            device_id=device_id,
            alias=alias if alias else None,
            device_password=device_password,
            user=request.user,
            update_interval=update_interval
        )
        messages.success(request, f"Device '{alias or device_id}' added successfully.")
        return redirect('device_list')
    
    return render(request, 'device/add_device.html')

@login_required
def device_login(request, device_id):
    if request.method == 'POST':
        device_password = request.POST.get('device_password')
        device = Device.objects.filter(device_id=device_id).first()
        if device and (device.user == request.user or DeviceShare.objects.filter(device=device, shared_with=request.user).exists()):
            if device.device_password == device_password:
                return redirect('dashboard', device_id=device_id)
            else:
                messages.error(request, "Invalid device credentials.")
        else:
            messages.error(request, "You do not have access to this device.")
    return render(request, 'device/device_login.html', {'device_id': device_id})

@login_required
def dashboard(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id)
        if device.user != request.user and not DeviceShare.objects.filter(device=device, shared_with=request.user).exists():
            messages.error(request, "You do not have access to this device.")
            return redirect('device_list')
        latest_data = DeviceData.objects.filter(device=device).order_by('-timestamp').first()
        notifications = Notification.objects.filter(device=device, user=request.user).order_by('-timestamp')[:10]
        data = {
            'deviceId': device.device_id,
            'alias': device.alias or device.device_id,
            'timestamp': 'No data',
            'location': {'latitude': 0, 'longitude': 0, 'altitude': 0},
            'speed': 0,
            'heading': 0,
            'charge': 0,
            'total_distance': 0,
            'has_data': False,
            'power_source': 'unknown',
            'battery_status': 'unknown',
            'is_on': False
        }
        if latest_data:
            data.update({
                'timestamp': latest_data.timestamp.isoformat(),
                'location': {
                    'latitude': latest_data.latitude,
                    'longitude': latest_data.longitude,
                    'altitude': latest_data.altitude
                },
                'speed': latest_data.speed,
                'heading': latest_data.heading,
                'charge': latest_data.charge,
                'has_data': True,
                'power_source': latest_data.power_source,
                'battery_status': f"{latest_data.charge}% ({'Charging' if latest_data.power_source == 'direct' else 'Discharging'})",
                'is_on': latest_data.speed > 0 or (timezone.now() - latest_data.timestamp).total_seconds() / 60 < 10
            })
        time_threshold = timezone.now() - timedelta(hours=24)
        data_points = DeviceData.objects.filter(device=device, timestamp__gte=time_threshold).order_by('timestamp')
        data['total_distance'] = calculate_total_distance(data_points) / 1000
        maintenance = MaintenanceRecord.objects.filter(device=device).order_by('-timestamp').first()
        data['maintenance_status'] = maintenance.status if maintenance else "No maintenance records"
        return render(request, 'device/dashboard.html', {'device': device, 'data': data, 'notifications': notifications})
    except Device.DoesNotExist:
        messages.error(request, "Device not found.")
        return redirect('device_list')

@login_required
@csrf_protect
def save_device_data(request, device_id):
    if request.method != 'POST':
        return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)
    try:
        device = Device.objects.get(device_id=device_id)
        if device.user != request.user and not DeviceShare.objects.filter(device=device, shared_with=request.user).exists():
            return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)
        data = json.loads(request.body)
        required_fields = ['location', 'charge', 'timestamp', 'power_source']
        required_location_fields = ['latitude', 'longitude', 'altitude']
        if not all(key in data for key in required_fields) or not all(key in data['location'] for key in required_location_fields):
            return JsonResponse({"status": "error", "message": "Missing required fields"}, status=400)
        try:
            latitude = float(data['location']['latitude'])
            longitude = float(data['location']['longitude'])
            altitude = float(data['location']['altitude'])
            speed = float(data.get('speed', 0))
            heading = float(data.get('heading', 0))
            charge = int(data['charge'])
            power_source = data['power_source']
            parsed_timestamp = parse_timestamp(data['timestamp'])
            if not parsed_timestamp:
                return JsonResponse({"status": "error", "message": "Invalid timestamp format"}, status=400)
            if power_source == 'battery' and not request.user.is_admin:
                latest_data = DeviceData.objects.filter(device=device).order_by('-timestamp').first()
                if latest_data:
                    time_diff = (parsed_timestamp - latest_data.timestamp).total_seconds() / 60
                    if time_diff < device.update_interval:
                        return JsonResponse({"status": "error", "message": "Update interval not reached"}, status=429)
            device_data = DeviceData.objects.create(
                device=device,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                charge=charge,
                timestamp=parsed_timestamp,
                power_source=power_source,
                speed=speed,
                heading=heading
            )
            return JsonResponse({"status": "success"})
        except (ValueError, TypeError) as e:
            return JsonResponse({"status": "error", "message": f"Invalid data types: {str(e)}"}, status=400)
        except IntegrityError:
            return JsonResponse({"status": "error", "message": "Duplicate timestamp for this device"}, status=400)
    except Device.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Device not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
    except Exception as e:
        print(f"save_device_data: Unexpected error: {str(e)}")
        return JsonResponse({"status": "error", "message": "Server error"}, status=500)

@login_required
def device_history(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id)
        if device.user != request.user and not DeviceShare.objects.filter(device=device, shared_with=request.user).exists():
            messages.error(request, "You do not have access to this device.")
            return redirect('device_list')
        return render(request, 'device/device_history.html', {'device': device})
    except Device.DoesNotExist:
        messages.error(request, "Device not found.")
        return redirect('device_list')

@login_required
def device_history_data(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id)
        if device.user != request.user and not DeviceShare.objects.filter(device=device, shared_with=request.user).exists():
            return JsonResponse({"error": "Unauthorized"}, status=403)
        query = DeviceData.objects.filter(device=device).order_by('-timestamp')
        time_threshold = request.GET.get('time_threshold')
        limit = request.GET.get('limit')
        if time_threshold:
            parsed_threshold = parse_timestamp(time_threshold)
            if not parsed_threshold:
                return JsonResponse({"error": "Invalid time threshold format"}, status=400)
            query = query.filter(timestamp__gte=parsed_threshold)
        data_points = query.all()
        if limit:
            try:
                data_points = data_points[:int(limit)]
            except ValueError:
                return JsonResponse({"error": "Invalid limit parameter"}, status=400)
        if not data_points:
            return JsonResponse({"error": "No data points available for this time range"}, status=404)
        points = [{
            "latitude": point.latitude,
            "longitude": point.longitude,
            "timestamp": point.timestamp.isoformat(),
            "speed": point.speed,
            "heading": point.heading,
            "altitude": point.altitude,
            "charge": point.charge,
            "power_source": point.power_source
        } for point in data_points]
        distance_query = DeviceData.objects.filter(
            device=device,
            timestamp__gte=(parse_timestamp(time_threshold) or timezone.now() - timedelta(hours=24))
        ).order_by('timestamp')
        total_distance = calculate_total_distance(distance_query) / 1000
        return JsonResponse({
            "data_points": points,
            "count": len(points),
            "total_distance": total_distance
        })
    except Device.DoesNotExist:
        return JsonResponse({"error": "Device not found"}, status=404)

@login_required
def device_data(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id)
        if device.user != request.user and not DeviceShare.objects.filter(device=device, shared_with=request.user).exists():
            messages.error(request, "You do not have access to this device.")
            return redirect('device_list')
        data_points = DeviceData.objects.filter(device=device).order_by('timestamp')
        metrics = {
            'total_distance': 0,
            'average_speed': 0,
            'max_speed': 0,
            'min_speed': 0,
            'weekly_data': {'total_distance': 0, 'average_speed': 0},
            'rash_driving_instances': 0,
            'vehicle_status_changes': 0,
            'weekly_travel_speed': 0
        }
        if data_points.exists():
            metrics['total_distance'] = calculate_total_distance(data_points) / 1000
            metrics['average_speed'] = data_points.aggregate(Avg('speed'))['speed__avg'] or 0
            metrics['max_speed'] = data_points.aggregate(Max('speed'))['speed__max'] or 0
            metrics['min_speed'] = data_points.aggregate(Min('speed'))['speed__min'] or 0
            one_week_ago = timezone.now() - timedelta(days=7)
            weekly_data = DeviceData.objects.filter(device=device, timestamp__gte=one_week_ago)
            metrics['weekly_data'] = {
                'total_distance': calculate_total_distance(weekly_data) / 1000,
                'average_speed': weekly_data.aggregate(Avg('speed'))['speed__avg'] or 0
            }
            metrics['weekly_travel_speed'] = metrics['weekly_data']['average_speed']
            rash_threshold = 80
            metrics['rash_driving_instances'] = SpeedAlert.objects.filter(device=device, speed__gt=rash_threshold).count()
            status_changes = 0
            last_status = None
            last_timestamp = None
            for point in data_points:
                current_status = 'on' if point.speed > 0 else 'off'
                if last_status is None:
                    last_status = current_status
                    last_timestamp = point.timestamp
                elif current_status != last_status:
                    if current_status == 'off':
                        time_diff = (point.timestamp - last_timestamp).total_seconds() / 60
                        if time_diff >= 10:
                            status_changes += 1
                            last_status = current_status
                    else:
                        status_changes += 1
                        last_status = current_status
                last_timestamp = point.timestamp
            metrics['vehicle_status_changes'] = status_changes
        return render(request, 'device/device_data.html', {'device': device, 'metrics': metrics})
    except Device.DoesNotExist:
        messages.error(request, "Device not found.")
        return redirect('device_list')

@login_required
def share_device(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id, user=request.user)
        if request.method == 'POST':
            email = request.POST.get('email')
            if DeviceShare.objects.filter(device=device).count() >= 3:
                messages.error(request, "Maximum 3 users can be shared with.")
                return render(request, 'device/share_device.html', {'device': device})
            try:
                shared_with = User.objects.get(email=email)
                DeviceShare.objects.create(
                    device=device,
                    shared_with=shared_with,
                    permission='view'  # Only view permission
                )
                messages.success(request, f"Device shared with {shared_with.username}.")
                return redirect('device_list')
            except User.DoesNotExist:
                messages.error(request, "No user found with this email.")
                return render(request, 'device/share_device.html', {'device': device})
        return render(request, 'device/share_device.html', {'device': device})
    except Device.DoesNotExist:
        messages.error(request, "Device not found.")
        return redirect('device_list')


@login_required
def manage_all_shares(request):
    devices = Device.objects.filter(user=request.user)
    shares = DeviceShare.objects.filter(device__in=devices)

    if request.method == 'POST':
        share_id = request.POST.get('share_id')
        action = request.POST.get('action')
        try:
            share = DeviceShare.objects.get(id=share_id, device__in=devices)
            if action == 'delete':
                share.delete()
                messages.success(request, "Share removed successfully.")
        except DeviceShare.DoesNotExist:
            messages.error(request, "Share not found.")
        return redirect('manage_all_shares')

    return render(request, 'device/manage_all_shares.html', {'devices': devices, 'shares': shares})

@login_required
def maintenance_status(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id, user=request.user)
        if request.method == 'POST':
            status = request.POST.get('status', 'Maintenance required')
            MaintenanceRecord.objects.create(
                device=device,
                status=status,
                timestamp=timezone.now()
            )
            messages.success(request, "Maintenance status updated.")
            return redirect('dashboard', device_id=device_id)
        records = MaintenanceRecord.objects.filter(device=device).order_by('-timestamp')
        return render(request, 'device/maintenance_status.html', {'device': device, 'records': records})
    except Device.DoesNotExist:
        messages.error(request, "Device not found.")
        return redirect('device_list')

@login_required
def edit_device(request, device_id):
    try:
        device = Device.objects.get(device_id=device_id, user=request.user)
        if request.method == 'POST':
            new_device_id = request.POST.get('device_id')
            alias = request.POST.get('alias')
            device_password = request.POST.get('device_password')
            update_interval = request.POST.get('update_interval', device.update_interval)
            
            if not new_device_id:
                messages.error(request, 'Device ID is required.')
                return render(request, 'device/edit_device.html', {'device': device})
            
            if new_device_id != device.device_id and Device.objects.filter(device_id=new_device_id).exists():
                messages.error(request, 'Device ID already exists.')
                return render(request, 'device/edit_device.html', {'device': device})
            
            try:
                update_interval = int(update_interval)
                if update_interval < 1:
                    raise ValueError
            except ValueError:
                messages.error(request, 'Invalid update interval.')
                return render(request, 'device/edit_device.html', {'device': device})
            
            device.device_id = new_device_id
            device.alias = alias if alias else None
            if device_password:
                device.device_password = device_password
            device.update_interval = update_interval
            device.save()
            messages.success(request, f"Device '{device.alias or device.device_id}' updated successfully.")
            return redirect('device_list')
        
        return render(request, 'device/edit_device.html', {'device': device})
    except Device.DoesNotExist:
        messages.error(request, 'Device not found or you do not own it.')
        return redirect('device_list')

@login_required
def notifications(request):
    device_id = request.GET.get('device_id')
    time_threshold = request.GET.get('time_threshold')
    
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')
    speed_alerts = SpeedAlert.objects.filter(device__user=request.user).order_by('-timestamp')
    
    if device_id:
        try:
            device = Device.objects.get(device_id=device_id)
            if device.user != request.user and not DeviceShare.objects.filter(device=device, shared_with=request.user).exists():
                messages.error(request, 'You do not have access to this device.')
                return redirect('device_list')
            notifications = notifications.filter(device=device)
            speed_alerts = speed_alerts.filter(device=device)
        except Device.DoesNotExist:
            messages.error(request, 'Device not found.')
            return redirect('device_list')
    
    if time_threshold:
        try:
            parsed_threshold = parse_timestamp(time_threshold)
            if not parsed_threshold:
                messages.error(request, 'Invalid time threshold format.')
            else:
                notifications = notifications.filter(timestamp__gte=parsed_threshold)
                speed_alerts = speed_alerts.filter(timestamp__gte=parsed_threshold)
        except ValueError:
            messages.error(request, 'Invalid time threshold format.')
    
    devices = Device.objects.filter(user=request.user) | Device.objects.filter(deviceshare__shared_with=request.user)
    return render(request, 'device/notifications.html', {
        'notifications': notifications,
        'speed_alerts': speed_alerts,
        'devices': devices,
        'selected_device_id': device_id
    })

@login_required
def mark_notification_read(request, notification_id):
    if request.method == 'POST':
        try:
            notification = Notification.objects.get(id=notification_id, user=request.user)
            notification.read = True
            notification.save()
            return JsonResponse({"status": "success"})
        except Notification.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Notification not found"}, status=404)
    return JsonResponse({"status": "error", "message": "Invalid request method"}, status=405)

@login_required
def user_settings(request):
    
    # All notifications for the user (across all devices)
    notifications = Notification.objects.filter(user=request.user).order_by('-timestamp')[:10]
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        user = request.user
        if username and username != user.username:
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username is already taken.')
                return render(request, 'device/user_settings.html')
            user.username = username
        
        if email and email != user.email:
            if User.objects.filter(email=email).exists():
                messages.error(request, 'Email is already in use.')
                return render(request, 'device/user_settings.html')
            user.email = email
        
        if password:
            user.set_password(password)
            update_session_auth_hash(request, user)  # Keep user logged in after password change
        
        
        
        
        user.save()
        messages.success(request, 'Settings updated successfully.')
        return redirect('user_settings')
    
    return render(request, 'device/user_settings.html',{
                  'notifications': notifications})

@login_required
def subscriptions(request, device_id):
    # Fetch the device based on the device_id
    device = get_object_or_404(Device, device_id=device_id, user=request.user)
    
    # Example: Add subscription details (you'll need to adjust based on your model)
    device.plan_name = "Premium"  # Example value; fetch from your model or database
    device.plan_validity_days = 365  # Example value
    device.plan_expiration_date = "2026-05-26"  # Example value; calculate based on start date
    
    context = {
        'device': device,
    }
    return render(request, 'device/subscriptions.html', context)