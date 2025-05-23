from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password

class Command(BaseCommand):
    help = 'Quickly create 1000 users using bulk_create'

    def handle(self, *args, **kwargs):
        users_to_create = []
        password = make_password('testpass123')  # Pre-hash once

        for i in range(1, 1001):
            username = f'user{i}'
            email = f'user{i}@example.com'
            if not User.objects.filter(username=username).exists():
                users_to_create.append(User(username=username, email=email, password=password))

        User.objects.bulk_create(users_to_create)
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully created {len(users_to_create)} users.'))
