import csv
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from device.models import Device, DeviceData

from datetime import datetime

class Command(BaseCommand):
    help = 'Import 1000 devices from CSV, create 1000 users, and assign each device to a user'

    def handle(self, *args, **kwargs):
        csv_file = 'devices_export.csv'
        with open(csv_file, newline='') as file:
            reader = list(csv.DictReader(file))

        if len(reader) < 1000:
            self.stdout.write(self.style.ERROR('CSV file must contain at least 1000 devices'))
            return

        # Step 1: Create 1000 users (if not already present)
        password_hash = make_password('testpass123')
        users_to_create = []
        for i in range(1, 1001):
            username = f'user{i}'
            if not User.objects.filter(username=username).exists():
                users_to_create.append(User(username=username, email=f'{username}@example.com', password=password_hash))

        User.objects.bulk_create(users_to_create)
        self.stdout.write(self.style.SUCCESS(f'Created {len(users_to_create)} users (skipped existing).'))

        # Fetch all users again (existing + new) in order
        users = list(User.objects.filter(username__regex=r'^user\d+$').order_by('username')[:1000])

        # Step 2: Import devices and assign to users
        created_devices = []
        for i in range(1000):
            row = reader[i]
            device_id = row['device_id'].strip()
            device_password = row['device_password'].strip()
            latitude = float(row['latitude'])
            longitude = float(row['longitude'])
            charge = int(row['charge'])

            if Device.objects.filter(device_id=device_id).exists():
                continue  # Skip if already exists

            created_devices.append(Device(
                user=users[i],
                device_id=device_id,
                device_password=device_password
            ))

        Device.objects.bulk_create(created_devices)
        self.stdout.write(self.style.SUCCESS(f'Imported {len(created_devices)} devices and assigned users.'))

        # Step 3: Create one DeviceData entry per device
        all_devices = list(Device.objects.filter(device_id__in=[r['device_id'].strip() for r in reader[:1000]]))
        device_data = []
        for i, device in enumerate(all_devices):
            row = reader[i]
            device_data.append(DeviceData(
                device=device,
                latitude=float(row['latitude']),
                longitude=float(row['longitude']),
                charge=int(row['charge']),
                timestamp=datetime.now()
            ))
        DeviceData.objects.bulk_create(device_data)
        self.stdout.write(self.style.SUCCESS(f'Inserted {len(device_data)} device data entries.'))

        self.stdout.write(self.style.SUCCESS('\n✅ Done: 1000 users + devices + data imported.'))
