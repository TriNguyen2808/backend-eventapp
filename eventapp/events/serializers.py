from django.template.context_processors import request
from django.conf import settings
from .models import (
    User, Event,TicketClass, Ticket, Payment, Notification, Rating,
    Report, ChatMessage, EventSuggestion, DiscountCode, Like, Comment
)
from django.utils.timezone import now
from datetime import datetime
from rest_framework import serializers
from urllib.parse import quote
import unicodedata, random, string, qrcode, os
class EventSerializer(serializers.ModelSerializer):

    class Meta:
        model = Event
        fields = ['id', 'name', 'image', 'user', 'event_type', 'location', 'description', 'start_time', 'end_time','active', 'popularity_score']
        read_only_fields = ['id','user', 'active', 'popularity_score']

    def get_image(self, event):

        if event.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri('/static/%s' % event.image.name)
            return '/static/%s' % event.image.name

    def create(self, validated_data):
        user = self.context['request'].user
        location = validated_data.pop('location', '')

        # Tạo URL Google Maps
        location_url = f"https://www.google.com/maps/search/?api=1&query={quote(location)}"

        # Tạo sự kiện
        event = Event.objects.create(
            user=user,
            location=location_url,
            **validated_data
        )
        return event


class TicketClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketClass
        fields = ['id','name','price','type','total_available']
        read_only_fields = ['id']

    def create(self, validated_data):
        event = self.context.get('event')
        return TicketClass.objects.create(event=event, **validated_data)


class EventDetailSerializer(EventSerializer):
    liked = serializers.SerializerMethodField()

    def get_liked(self,event):
        request = self.context.get('request')
        if request.user.is_authenticated:
            return event.like_set.filter(active=True).exists()

    class Meta:
        model = EventSerializer.Meta.model
        fields = EventSerializer.Meta.fields + ['liked']

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['first_name','last_name','avatar','email','username','password','role', 'group']
        read_only_fields = ['group']
        extra_kwargs ={
            'password':{
                'write_only': True
            }
        }

    #Đăng ký
    def create(self, validated_data):
        data = validated_data.copy()
        role = data.get('role')
        user = User(**data)
        user.set_password(data['password'])
        if role.id == 1:
            user.is_superuser = True
        user.save()
        return user


class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = Comment
        fields = ['id','content', 'event','user']


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ['ticket_class']

    def validate(self, attrs):
        ticket_class = attrs['ticket_class']
        if ticket_class.total_available <= 0:
            raise serializers.ValidationError("Hạng vé đã bán hết.")
        return attrs

    def create_qr_image(ticket_code):
        now = datetime.now()
        # Tạo mã QR từ ticket_code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(ticket_code)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Đường dẫn lưu file
        qr_folder = os.path.join(
            settings.MEDIA_ROOT,
            'ticket_qr',
            now.strftime('%Y'),
            now.strftime('%m')
        )
        os.makedirs(qr_folder, exist_ok=True)  # Tạo thư mục nếu chưa có

        file_path = os.path.join(qr_folder, f'{ticket_code}.png')
        img.save(file_path)
        return file_path


    def create(self, validated_data):
        user = self.context['request'].user
        ticket_class = validated_data['ticket_class']
        event = ticket_class.event

        # Rút gọn: Tên viết tắt không dấu
        initials = ''.join([
            unicodedata.normalize('NFD', w)[0].upper()
            for w in event.name.split()
            if w  # bỏ qua từ rỗng
        ])
        initials = ''.join(
            c for c in unicodedata.normalize('NFD', initials)
            if unicodedata.category(c) != 'Mn'
        )

        event_date_str = event.start_time.strftime('%d%m%Y')
        ticket_code = ''
        while True:
            suffix = ''.join(random.choices(string.digits, k=6))  # Tạo 6 số ngẫu nhiên
            code = f"{initials}-{event_date_str}-{suffix}"
            if not Ticket.objects.filter(ticket_code=ticket_code).exists():  # Kiểm tra mã vé có bị trùng không
                ticket_code = code
                break

        ticket_class.total_available -= 1
        ticket_class.save()

        ticket = Ticket.objects.create(
            user=user,
            ticket_class=ticket_class,
            price_paid=ticket_class.price,
            ticket_code=ticket_code
        )
        return ticket


class QRCheckInSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ['ticket_code', 'is_checked_in', 'checkin_time']
        read_only_fields = ['is_checked_in', 'checkin_time']

    # def validate_ticket_code(self, ticket_code):
    #     try:
    #         ticket = Ticket.objects.get(ticket_code=code)
    #     except Ticket.DoesNotExist:
    #         raise serializers.ValidationError("Mã vé không hợp lệ.")
    #
    #     if ticket.checked_in:
    #         raise serializers.ValidationError("Vé đã được check-in trước đó.")
    #     return ticket_code
