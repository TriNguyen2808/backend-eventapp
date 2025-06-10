from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

class Command(BaseCommand):
    help = 'Gửi email test để kiểm tra cấu hình email'

    def handle(self, *args, **options):
        try:
            send_mail(
                subject='🔔 Kiểm tra email từ Django',
                message='✅ Đây là email test từ hệ thống của bạn.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.EMAIL_HOST_USER],  # Gửi về chính mình
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('✅ Email đã được gửi thành công!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Gửi email thất bại: {e}'))
