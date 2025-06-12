from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from ckeditor.fields import RichTextField
import random, string
from unidecode import unidecode
from cloudinary.models import CloudinaryField
from django.db.models import Sum
from django.utils import timezone
from django import forms
import unicodedata

class Role(models.Model):  # phan quyen
    class RoleName(models.TextChoices):  # enum ten quyen
        ADMIN = 'ADMIN'
        ORGANIZER = 'ORGANIZER'
        ATTENDEE = 'ATTENDEE'

    name = models.CharField(max_length=20, choices=RoleName.choices, unique=True)  # ten vai

    def __str__(self):
        return self.name


class CustomerGroup(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    spending_goal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def __str__(self):
        return self.name


class User(AbstractUser):  # nguoi dung
    email = models.EmailField(unique=True)  # email la duy nhat
    avatar = CloudinaryField('avatar', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # thoi gian tao
    updated_at = models.DateTimeField(auto_now=True)  # thoi gian cap nhat
    role = models.ForeignKey(Role, on_delete=models.CASCADE, default=3)
    group = models.ForeignKey(CustomerGroup, on_delete=models.CASCADE, default=1)

    def __str__(self):
        return self.username

    def update_group(self):
        total_spending = Ticket.objects.filter(user=self).aggregate(total=Sum('price_paid'))['total'] or 0

        # Sắp xếp nhóm theo spending_goal tăng dần
        groups = CustomerGroup.objects.order_by('spending_goal')

        matched_group = None
        for i, group in enumerate(groups):
            current_goal = group.spending_goal
            next_goal = groups[i + 1].spending_goal if i + 1 < len(groups) else float('inf')

            if current_goal <= total_spending < next_goal:
                matched_group = group
                break

        # Cập nhật nếu khác
        if matched_group and self.group != matched_group:
            self.group = matched_group
            self.save(update_fields=["group"])

    class Meta:
        ordering = ['-created_at']


# class UserRole(models.Model):  #quyen cua nguoi dung
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     role = models.ForeignKey(Role, on_delete=models.CASCADE)
#
#     class Meta:
#         unique_together = ('user', 'role')  #moi cap user-role la duy nhat

class EventType(models.Model):
    name = models.CharField(max_length=100, primary_key=True)

    def __str__(self):
        return self.name


class Event(models.Model):  # thong tin su kien
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # nguoi to chuc
    name = models.CharField(max_length=255)  # ten
    image = CloudinaryField('image', null=True, blank=True)
    description = RichTextField(blank=True, null=True)  # mo ta
    event_type = models.ForeignKey(EventType, to_field='name', on_delete=models.SET_NULL, null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, null=True)  # dia diem to chuc
    start_time = models.DateTimeField()  # thoi gian bat dau
    end_time = models.DateTimeField()  # thoi gian ket thuc
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)  # thoi gian tao su kien
    updated_at = models.DateTimeField(auto_now=True)  # thoi gian update su
    popularity_score = models.FloatField(default=0)

    def __str__(self):
        return self.name

    def update_popularity(self):
        ticket_count = Ticket.objects.filter(ticket_class__event=self).count()
        like_count = self.like_set.count()
        comment_count = self.comment_set.count()
        self.popularity_score = ticket_count * 1.5 + like_count + comment_count * 0.5
        self.save()

    class Meta:
        ordering = ['name']
        unique_together = ('name', 'start_time')

class UserPreference(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null = True)

    class Meta:
        unique_together = ('user', 'event_type')

class Interaction(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        abstract = True

class TicketClass(models.Model):
    class TicketType(models.TextChoices):
        STANDING = 'STANDING'
        SEATED = 'SEATED'

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticketclasses')  # Su kien lien ket
    name = models.CharField(max_length=100)  # Ten hang ve (VIP, Standard, Economy)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Gia ve
    type = models.CharField(max_length=20, choices=TicketType.choices, default='STANDING')  # Loai ve
    total_available = models.PositiveIntegerField(default=0)  # So luong co the ban

    def __str__(self):
        return f"{self.name} - {self.event.name}"

    class Meta:
        unique_together = ('event', 'name')
        ordering = ['event', 'name']


class Ticket(models.Model):

    ticket_class = models.ForeignKey(TicketClass, on_delete=models.CASCADE, null=True, related_name='tickets')  # Hang ve da chon
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # Nguoi mua ve
    ticket_code = models.CharField(max_length=100, unique=True)
    price_paid = models.DecimalField(max_digits=10, decimal_places=2, blank=True)  # Cho phép để trống ban đầu
    is_checked_in = models.BooleanField(default=False)
    checkin_time = models.DateTimeField(null=True, blank=True)
    booked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ticket_class.name} - {self.ticket_code}"

    class Meta:
        ordering = ['ticket_class', 'booked_at']

    def generate_ticket_code(event):
        # Tạo tên viết tắt từ tên sự kiện (không dấu, viết hoa chữ cái đầu)
        initials = ''.join([
            unicodedata.normalize('NFD', word)[0].upper()
            for word in event.name.split() if word
        ])
        initials = ''.join(
            c for c in unicodedata.normalize('NFD', initials)
            if unicodedata.category(c) != 'Mn'
        )

        event_date_str = event.start_time.strftime('%d%m%Y')

        while True:
            suffix = ''.join(random.choices(string.digits, k=6))
            ticket_code = f"{initials}-{event_date_str}-{suffix}"
            if not Ticket.objects.filter(ticket_code=ticket_code).exists():
                return ticket_code


class Notification(models.Model):  # thong bao
    class NotificationType(models.TextChoices):  # enum loai thong bao
        REMINDER = 'REMINDER'
        UPDATE = 'UPDATE'
        GENERAL = 'GENERAL'

    user = models.ForeignKey(User, on_delete=models.CASCADE)  # nguoi nhan
    message = RichTextField()  # noi dung thong bao
    type = models.CharField(max_length=20, choices=NotificationType.choices)  # loai thong bao
    is_read = models.BooleanField(default=False)  # da doc hay chua
    created_at = models.DateTimeField(auto_now_add=True)  # thoi gian tao thong bao


class Comment(Interaction):
    content = models.CharField(max_length=255, null=False)

class Like(Interaction):
    active=models.BooleanField(default=True)

    class Meta:
        unique_together = ('user','event')

class Rating(Interaction):  # danh gia su kien
    rate = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], default=0)  # diem danh gia (1-5)
    comment = RichTextField(blank=True, null=True)  # binh luan



class Report(models.Model):  # bao cao su kien
    event = models.ForeignKey(Event, on_delete=models.CASCADE)  # su kien duoc bao cao
    total_tickets_sold = models.IntegerField(default=0)  # so ve da ban
    total_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # doanh thu
    interest_score = models.IntegerField(default=0)  # chi so quan tam
    generated_at = models.DateTimeField(auto_now_add=True)  # thoi diem tao bao cao


class ChatRoom(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages', null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True, null=True)


class EventSuggestion(models.Model):  # goi y su kien theo so thich
    class PreferenceType(models.TextChoices):  # enum loai so thich
        MUSIC = 'MUSIC'
        CONFERENCE = 'CONFERENCE'
        SPORTS = 'SPORTS'
        OTHER = 'OTHER'

    user = models.ForeignKey(User, on_delete=models.CASCADE)  # nguoi dung
    preferred_type = models.CharField(max_length=20, choices=PreferenceType.choices)  # so thich su kien
    created_at = models.DateTimeField(auto_now_add=True)  # thoi gian tao goi y

class DiscountType(models.Model):
    name = models.CharField(max_length=20, unique=True)  # 'FIXED', 'PERCENTAGE'
    description = models.CharField(max_length=255)       # 'Giảm theo số tiền', 'Giảm theo %'

    def __str__(self):
        return self.name

class DiscountCode(models.Model):
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    valid_from = models.DateTimeField(null=True, blank=True)  # ngay bat dau hieu luc
    valid_to = models.DateTimeField(null=True, blank=True)  # ngay het hieu luc
    groups = models.ManyToManyField(CustomerGroup, related_name='discount_codes')
    max_usage = models.PositiveIntegerField(default=1)
    discount_type = models.ForeignKey(DiscountType, on_delete=models.CASCADE, related_name='discount_types', null=True)
    discount_value = models.FloatField(default=0)
    limit_discount = models.BooleanField(default=False)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    events = models.ManyToManyField(Event, blank=True)
    used_by = models.ManyToManyField(User, related_name='used_discounts', blank=True)

    def __str__(self):
        return self.code


class PaymentLog(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Chờ thanh toán'),
        ('success', 'Đã thanh toán'),
        ('failed', 'Thất bại'),
        ('expired', 'Hết hạn'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    ticket_class = models.ForeignKey(TicketClass, on_delete=models.CASCADE)
    discount_code = models.ForeignKey(DiscountCode, null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)  # Mã giao dịch từ VNPay
    ticket = models.OneToOneField('Ticket', null=True, blank=True, on_delete=models.SET_NULL)  # nếu tạo ticket sau thanh toán

    def is_expired(self, timeout_minutes=15):
        return self.status == 'pending' and (timezone.now() - self.created_at).total_seconds() > timeout_minutes * 60

    def __str__(self):
        return f"Payment #{self.pk} - {self.user} - {self.amount} VND - {self.status}"


class PaymentVNPay(models.Model):
    order_id = models.BigIntegerField(default=0, null=True, blank=True)
    amount = models.FloatField(default=0, null=True, blank=True)
    order_desc = models.CharField(max_length=200, null=True, blank=True)
    vnp_TransactionNo = models.CharField(max_length=200, null=True, blank=True)
    vnp_ResponseCode = models.CharField(max_length=200, null=True, blank=True)

class PaymentForm(forms.Form):
    order_id = forms.CharField(max_length=250)
    order_type = forms.CharField(max_length=20)
    amount = forms.IntegerField()
    order_desc = forms.CharField(max_length=100)
    bank_code = forms.CharField(max_length=20, required=False)
    language = forms.CharField(max_length=2)
