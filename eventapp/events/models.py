from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from ckeditor.fields import RichTextField
import random, string
from unidecode import unidecode
from cloudinary.models import CloudinaryField


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
    avatar = CloudinaryField('avatar', null=True)
    created_at = models.DateTimeField(auto_now_add=True)  # thoi gian tao
    updated_at = models.DateTimeField(auto_now=True)  # thoi gian cap nhat
    role = models.ForeignKey(Role, on_delete=models.CASCADE, default=3)
    group = models.ForeignKey(CustomerGroup, on_delete=models.CASCADE, default=1)

    def __str__(self):
        return self.username

    def update_group(self):
        pass

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
    image = models.ImageField(upload_to='events/%Y/%m', null=True)
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

    # def save(self, *args, **kwargs):
    #     if not self.price_paid and self.ticket_class:
    #         self.price_paid = self.ticket_class.price
    #
    #         # Tự động tạo mã vé khi có ticket_class và user
    #         if self.ticket_class and self.user:
    #             if not self.ticket_code:  # Nếu ticket_code chưa được tạo
    #                 event_name = self.ticket_class.event.name  # Lấy tên sự kiện từ TicketClass
    #                 event_name_no_accents = unidecode(event_name)  # Loại bỏ dấu tiếng Việt
    #                 prefix = ''.join([word[0].upper() for word in
    #                                   event_name_no_accents.split()])  # Lấy chữ cái đầu các từ trong tên sự kiện
    #                 while True:
    #                     suffix = ''.join(random.choices(string.digits, k=6))  # Tạo 6 số ngẫu nhiên
    #                     code = f"{prefix}{suffix}"
    #                     if not Ticket.objects.filter(ticket_code=code).exists():  # Kiểm tra mã vé có bị trùng không
    #                         self.ticket_code = code
    #                         break
    #
    #     super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket_class.name} - {self.ticket_code}"

    class Meta:
        ordering = ['ticket_class', 'booked_at']


class Payment(models.Model):  # thanh toan
    class PaymentMethod(models.TextChoices):  # enum phuong thuc thanh toan
        MOMO = 'MOMO'
        VNPAY = 'VNPAY'
        CREDIT_CARD = 'CREDIT_CARD'

    class PaymentStatus(models.TextChoices):  # enum trang thai thanh toan
        SUCCESS = 'SUCCESS'
        FAILED = 'FAILED'
        PENDING = 'PENDING'

    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    ticket_class = models.ForeignKey(TicketClass, on_delete=models.CASCADE, null=True)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)  # phuong thuc thanh toan
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # so tien thanh toan
    status = models.CharField(max_length=10, choices=PaymentStatus.choices, default='PENDING')  # trang thai
    payment_time = models.DateTimeField(auto_now_add=True)  # thoi gian thanh toan


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
    valid_from = models.DateField(null=True, blank=True)  # ngay bat dau hieu luc
    valid_to = models.DateField(null=True, blank=True)  # ngay het hieu luc
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