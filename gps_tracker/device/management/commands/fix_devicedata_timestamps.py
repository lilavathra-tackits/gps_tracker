from django.core.management.base import BaseCommand
from django.utils import timezone
from device.models import DeviceData

class Command(BaseCommand):
    help = 'Convert offset-naive timestamps in DeviceData to offset-aware (UTC)'

    def handle(self, *args, **kwargs):
        updated = 0
        for data in DeviceData.objects.all():
            if data.timestamp.tzinfo is None:
                # Assume naive timestamps are in UTC and make them aware
                data.timestamp = data.timestamp.replace(tzinfo=timezone.utc)
                data.save()
                updated += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Updated timestamp for DeviceData ID {data.id}: {data.timestamp}"
                ))
        self.stdout.write(self.style.SUCCESS(
            f"Updated {updated} DeviceData records to offset-aware timestamps"
        ))