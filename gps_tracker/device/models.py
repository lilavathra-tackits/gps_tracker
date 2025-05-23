from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Device(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    alias = models.CharField(max_length=100, blank=True, null=True)
    device_id = models.CharField(max_length=100, unique=True)
    device_password = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    update_interval = models.IntegerField(default=60)

    def __str__(self):
        return self.alias or self.device_id


class DeviceData(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField(default=0)
    speed = models.FloatField(default=0)
    heading = models.FloatField(default=0)
    charge = models.IntegerField(default=0)
    timestamp = models.DateTimeField(default=timezone.now)
    power_source = models.CharField(max_length=20, choices=[('battery', 'Battery'), ('direct', 'Direct')], default='battery')

    class Meta:
        unique_together = ('device', 'timestamp')
        indexes = [
            models.Index(fields=['device', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.device.device_id} at {self.timestamp}"


class SpeedAlert(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    message = models.CharField(max_length=200)
    speed = models.FloatField()
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.device.device_id}: {self.message} at {self.timestamp}"


class DeviceShare(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    shared_with = models.ForeignKey(User, on_delete=models.CASCADE)
    permission = models.CharField(max_length=20, choices=[('view', 'View'), ('edit', 'Edit')], default='view')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('device', 'shared_with')

    def __str__(self):
        return f"{self.device.device_id} shared with {self.shared_with.username}"


class Notification(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField(max_length=200)
    timestamp = models.DateTimeField(default=timezone.now)
    read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.device.device_id}: {self.message} for {self.user.username}"


class MaintenanceRecord(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    status = models.CharField(max_length=100, default="Maintenance required")
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.device.device_id}: {self.status} at {self.timestamp}"