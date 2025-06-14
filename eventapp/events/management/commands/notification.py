from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils.timezone import now
from datetime import timedelta
from django.conf import settings
from events.models import Event, Ticket

class Command(BaseCommand):
    help = "Gửi email nhắc nhở các sự kiện sắp diễn ra sau 3 ngày"

    def handle(self, *args, **kwargs):
        today = now()
        target_date = today + timedelta(days=3)
        events = Event.objects.filter(start_time__date__lte = target_date, active=True)
        sent_count = 0

        for event in events:
            tickets = Ticket.objects.filter(ticket_class__event=event).select_related('user')

            for ticket in tickets:
                user = ticket.user
                if user.email:
                    send_mail(
                        subject=f"[Nhắc nhở] Sự kiện '{event.name}' sắp diễn ra",
                        message=(
                            f"Xin chào {user.first_name or user.username},\n\n"
                            f"Sự kiện bạn đã đặt vé: '{event.name}' sẽ diễn ra vào lúc {event.start_time.strftime('%H:%M %d/%m/%Y')}.\n"
                            "Hãy chuẩn bị tham gia đúng giờ nhé!\n\n"
                            "Cảm ơn bạn đã sử dụng hệ thống đặt vé của chúng tôi."
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False
                    )
                    sent_count += 1

        self.stdout.write(self.style.SUCCESS(f"Đã gửi {sent_count} email nhắc nhở thành công."))