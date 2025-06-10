from django.core.management.base import BaseCommand
from eventapp.events.models import PaymentLog
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Xóa hoặc đánh dấu hết hạn đơn thanh toán chưa xử lý sau X phút'

    def handle(self, *args, **kwargs):
        timeout_minutes = 15
        expired_time = timezone.now() - timedelta(minutes=timeout_minutes)
        expired_logs = PaymentLog.objects.filter(status='pending', created_at__lt=expired_time)

        count = expired_logs.update(status='expired')
        self.stdout.write(self.style.SUCCESS(f"{count} đơn thanh toán đã hết hạn."))
