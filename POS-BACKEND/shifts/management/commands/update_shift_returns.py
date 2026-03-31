from django.core.management.base import BaseCommand
from shifts.models import Shift

class Command(BaseCommand):
    help = 'Update return totals for all shifts'

    def handle(self, *args, **options):
        shifts = Shift.objects.all()
        for shift in shifts:
            shift.update_return_totals()
            self.stdout.write(f'Updated shift {shift.id}: returns={shift.total_returns}, count={shift.return_count}, net_sales={shift.net_sales}')
        self.stdout.write(self.style.SUCCESS(f'Updated {shifts.count()} shifts'))
