from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import UserProfile


class Command(BaseCommand):
    help = 'Create test users for development'

    def handle(self, *args, **options):
        self.stdout.write('Creating test users...\n')

        # Create admin user
        if not User.objects.filter(username='admin').exists():
            admin = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
            UserProfile.objects.create(user=admin, role='admin')
        admin = User.objects.get(username='admin')
        self.stdout.write(
            self.style.SUCCESS('Admin user: admin / admin123 (role: admin)')
        )

        # Create manager user
        if not User.objects.filter(username='manager').exists():
            manager = User.objects.create_user('manager', 'manager@test.com', 'manager123')
            UserProfile.objects.create(user=manager, role='manager')
        manager = User.objects.get(username='manager')
        self.stdout.write(
            self.style.SUCCESS('Manager user: manager / manager123 (role: manager)')
        )

        # Create cashier user
        if not User.objects.filter(username='cashier').exists():
            cashier = User.objects.create_user('cashier', 'cashier@test.com', 'cashier123')
            UserProfile.objects.create(user=cashier, role='cashier')
        cashier = User.objects.get(username='cashier')
        self.stdout.write(
            self.style.SUCCESS('Cashier user: cashier / cashier123 (role: cashier)')
        )

        self.stdout.write('\n' + self.style.WARNING('Login Credentials:'))
        self.stdout.write('  Admin:    admin / admin123')
        self.stdout.write('  Manager:  manager / manager123')
        self.stdout.write('  Cashier:  cashier / cashier123')
        self.stdout.write('\nUse these to test the manager administration features!')
