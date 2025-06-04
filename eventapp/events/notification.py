from django.core.management.base import BaseCommand
from django.utils.timezone import now, timedelta
from django.core.mail import send_mail
from django.conf import settings
from .models import (Event, TicketClass, Ticket, User)


class Command(BaseCommand):
    help = 'Gửi email nhắc nhở sự kiện còn 3 ngày nữa'

    def handle(self, *args, **kwargs):
        today = now().date()
        target_date = today + timedelta(days=3)

        events = Event.objects.filter(start_time__date=target_date, active=True)

        for event in events:
            tickets = Ticket.objects.filter(ticket_class__event=event).select_related('user')

            for ticket in tickets:
                user = ticket.user
                if user.email:
                    send_mail(
                        subject=f"[Nhắc nhở] Sự kiện '{event.name}' sắp diễn ra",
                        message=(
                            f"Xin chào {user.last_name},\n\n"
                            f"Sự kiện bạn đã đặt vé: '{event.name}' sẽ diễn ra vào lúc {event.start_time.strftime('%H:%M %d/%m/%Y')}.\n"
                            "Hãy chuẩn bị tinh thần thật thoải mái để tham gia sự kiện nhé!\n\n"
                            "Cảm ơn bạn đã sử dụng hệ thống đặt vé của chúng tôi."
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False
                    )

        self.stdout.write(self.style.SUCCESS("Đã gửi email nhắc nhở thành công"))