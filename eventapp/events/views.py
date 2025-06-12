from django.conf import settings
from rest_framework.response import Response
from . import serializers, paginators, perms, filters, vnpay
from rest_framework.decorators import action
from django.db.models import Count, Min, Max
from rest_framework import viewsets, generics, status, parsers, permissions
from django.utils.timezone import now
from datetime import timedelta
from django.core.mail import send_mail, EmailMessage
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from django.db import transaction
from oauth2_provider.views import TokenView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import hmac, hashlib
from oauth2_provider.models import AccessToken
from django.utils import timezone
import qrcode, os
from io import BytesIO
import uuid, json
from django.db.models import Value, CharField, Sum
from django.db.models.functions import Concat
from .momo import create_momo_payment
from django.db import transaction
from decimal import Decimal
from django.db.models.functions import TruncMonth, TruncYear


import hashlib
import hmac
import json
import urllib
import urllib.parse
import urllib.request
import random
import requests
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
from urllib.parse import quote as urlquote

from .models import PaymentForm
from .vnpay import vnpay


from .models import (
    CustomerGroup, User, Event, TicketClass, Ticket, PaymentLog, Notification, Rating,
    Report, ChatMessage, EventSuggestion, DiscountType, DiscountCode, Like, Comment, UserPreference, EventType, PaymentVNPay
)


# Event.
class EventViewSet(viewsets.ViewSet, generics.ListAPIView, generics.CreateAPIView, generics.DestroyAPIView, generics.UpdateAPIView):
    serializer_class = serializers.EventDetailSerializer
    pagination_class = paginators.EventPaginator
    permission_classes = [permissions.IsAuthenticated()]

    def get_queryset(self):
        q = self.request.query_params.get("q")
        if q:
            return Event.objects.filter(active=True, name__icontains=q)
        return Event.objects.filter(active=True)

    # Chung thuc
    def get_permissions(self):
        if self.action in ['add_comment', 'like']:
            return [permissions.IsAuthenticated(), perms.IsAttendee()]
        elif self.action in ['create']:
            return [permissions.IsAuthenticated(), perms.IsOrganizer()]
        elif self.action in ['destroy', 'update']:
            return [perms.OwnerIsAuthenticated()]
        return [permissions.IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return serializers.EventSerializer
        return serializers.EventDetailSerializer

    # Like event
    @action(methods=['post'], url_path='like', detail=True)
    def like(self, request, pk):
        like, created = Like.objects.get_or_create(user=request.user, event=self.get_object())
        if not created:
            like.active = not like.active
            like.save()
        return Response(serializers.EventDetailSerializer(self.get_object(), context={'request': request}).data,
                        status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        image_url = request.build_absolute_uri(event.image.url) if event.image else None
        response_data = {
            "statusCode": 201,
            "error": None,
            "message": "Create an event",
            "data": {
                "id": event.id,
                "name": event.name,
                "description": event.description,
                "location": event.location,
                "image": image_url,
                "start_time": event.start_time,
                "end_time": event.end_time,
                "event_type": event.event_type.name,
                "createdAt": event.created_at.isoformat(),
                "updatedAt": event.updated_at.isoformat() if event.updated_at else None,
                "createdBy": event.user.email if event.user else None,
            }
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        try:
            instance = self.get_object()
        except Event.DoesNotExist:
            return Response({
                "statusCode": 404,
                "message": "Không tìm thấy sự kiện để cập nhật"
            }, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            serializer.save()

            # 🔔 Lấy người đã mua vé
            users = User.objects.filter(ticket__ticket_class__event=instance).distinct()

            for user in users:
                # Gửi thông báo hệ thống
                # Notification.objects.create(
                #     user=user,
                #     message=f"Sự kiện '{instance.name}' bạn đã mua vé vừa được cập nhật.",
                # )

                # Gửi email
                send_mail(
                    subject=f"[Thông báo] Sự kiện '{instance.name}' đã được cập nhật",
                    message=(
                        f"Chào {user.get_full_name() or user.username},\n\n"
                        f"Sự kiện bạn đã đặt vé ('{instance.name}') đã có cập nhật mới.\n"
                        f"Thời gian: {instance.start_time.strftime('%d/%m/%Y %H:%M')} - {instance.end_time.strftime('%d/%m/%Y %H:%M')}\n"
                        f"Địa điểm: {instance.location}\n\n"
                        f"Vui lòng truy cập hệ thống để xem chi tiết.\n\n"
                        f"Trân trọng,\nĐội ngũ tổ chức sự kiện"
                    ),
                    from_email=None,  # Lấy từ DEFAULT_FROM_EMAIL
                    recipient_list=[user.email],
                    fail_silently=False
                )

            return Response({
                "statusCode": 200,
                "message": "Cập nhật sự kiện thành công và đã gửi thông báo + email cho người tham gia.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        return Response({
            "message": "Cập nhật sự kiện thất bại",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        try:
            event = Event.objects.get(pk=pk)  # Bỏ lọc active
        except Event.DoesNotExist:
            return Response({
                "statusCode": 404,
                "error": "Event not found.",
                "message": "Không tìm thấy sự kiện.",
                "data": None,
                "pk": pk,
                "user's role": request.user.role.name
            }, status=status.HTTP_404_NOT_FOUND)

        # Optional: chỉ organizer tạo event mới được xóa
        if request.user != event.user and not request.user.is_superuser:
            return Response({"detail": "Bạn không có quyền xóa sự kiện này."},
                            status=status.HTTP_403_FORBIDDEN)

        event.delete()
        return Response({
            "statusCode": 204,
            "error": None,
            "message": "Event deleted successfully.",
            "data": None
        }, status=status.HTTP_204_NO_CONTENT)

    # Nhan xet su kien
    @action(methods=['post'], url_path='comments', detail=True)
    def add_comment(self, request, pk):
        c = Comment.objects.create(user=request.user, event=self.get_object(), content=request.data.get('content'))
        event = Event.objects.get(pk=pk)
        event.update_popularity()
        response_data = {
            "statusCode": 201,
            "error": None,
            "message": "Create an event",
            "data": {
                "id": c.id,
                "content": c.content,
                "Full name": c.user.get_full_name(),
                "Event's name": c.event.name,
                "createdAt": c.created_at.isoformat(),
                "updatedAt": c.updated_at.isoformat() if c.updated_at else None,
            }
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    # Tim hang ve cua su kien
    @action(methods=['get'], detail=True)
    def ticketclasses(self, request, pk):
        event = self.get_object()
        if not event.active:
            return Response({"detail": "Event is not active."}, status=status.HTTP_404_NOT_FOUND)

        ticket_class = event.ticketclass_set.all()
        return Response({
            "statusCode": 200,
            "error": None,
            "message": "Fetch all ticket classes",
            "data": serializers.TicketClassSerializer(ticket_class, many=True).data
        },
            status=status.HTTP_200_OK)

    # Lọc danh sách comment của event
    @action(methods=['get'], detail=True)
    def list_comments(self, request, pk):
        event = self.get_object()
        if not event.active:
            return Response({"detail": "Event is not active."}, status=status.HTTP_404_NOT_FOUND)

        comments = event.comment_set.all().order_by('-created_at')
        page = self.paginate_queryset(comments)
        if page is not None:
            serializer = serializers.CommentSerializer(page, many=True)

            page_size = self.paginator.page_size
            current_page = self.paginator.page.number
            total_items = self.paginator.page.paginator.count
            total_pages = self.paginator.page.paginator.num_pages

            return Response({
                "statusCode": 200,
                "error": None,
                "message": "Fetch all comments",
                "data": {
                    "meta": {
                        "page": current_page,
                        "pageSize": page_size,
                        "pages": total_pages,
                        "total": total_items
                    },
                    "result": serializer.data
                }
            },
                status=status.HTTP_200_OK)

        # fallback nếu không phân trang
        serializer = serializers.CommentSerializer(comments, many=True)
        return Response({
            "statusCode": 200,
            "error": None,
            "message": "Fetch all comments",
            "data": {
                "meta": None,
                "result": serializer.data
            }
        })

    @action(detail=False, methods=['get'], url_path='suggested', url_name='suggested-events')
    def suggested_events(self, request):
        user = request.user

        # Cập nhật UserPreference cho user
        event_type_counts = (
            Ticket.objects.filter(user=user)
            .values('ticket_class__event__event_type')
            .annotate(total=Count('id'))
            .filter(total__gte=5)
        )

        if event_type_counts:
            # Xoá preferences cũ
            UserPreference.objects.filter(user=user).delete()

            # Tạo lại các preferences mới
            for item in event_type_counts:
                event_type_id = item['ticket_class__event__event_type']
                if event_type_id:
                    try:
                        event_type = EventType.objects.get(pk=event_type_id)
                        UserPreference.objects.create(user=user, event_type=event_type)
                    except EventType.DoesNotExist:
                        continue

            # Gợi ý các sự kiện dựa trên preferences mới
            preferred_types = UserPreference.objects.filter(user=user).values_list('event_type', flat=True)
            suggested_events = Event.objects.filter(
                event_type__in=preferred_types,
                active=True
            ).order_by('start_time')

            serializer = self.get_serializer(suggested_events, many=True)
            return Response({
                "statusCode": 200,
                "error": None,
                "user": {
                    "full_name": user.get_full_name(),
                    "email": user.email,
                    "preferred_event_types": [str(cat) for cat in preferred_types]
                },
                "message": "Suggested events based on your preferences",
                "data": serializer.data
            }, status=status.HTTP_200_OK)

        return Response({"message": "Không đủ dữ liệu để gợi ý (số vé đặt quá ít <5)."},
                        status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='hot', url_name='hot-events')
    def hot_events(self, request):
        hot_events = Event.objects.filter(active=True).order_by('-popularity_score')[:5]
        serializer = self.get_serializer(hot_events, many=True)
        return Response({
            "statusCode": 200,
            "error": None,
            "message": "hot events",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        queryset = Event.objects.filter(active=True)
        today = now().date()
        period = request.query_params.get('period')
        name = request.query_params.get('name')
        event_type = request.query_params.get('event_type')
        min_price = request.query_params.get('min_price')
        max_price = request.query_params.get('max_price')

        if period == 'today':
            queryset = Event.objects.filter(start_time__date=today)
        elif period == 'week':
            start = today
            end = today + timedelta(days=7)
            queryset = Event.objects.filter(start_time__date__range=(start, end))
        elif period == 'month':
            start = today.replace(day=1)
            end = (start + timedelta(days=31)).replace(day=1) - timedelta(days=1)
            queryset = Event.objects.filter(start_time__date__range=(start, end))

        if name:
            queryset = Event.objects.filter(name__icontains=name)

        if event_type:
            queryset = queryset.filter(event_type__name__iexact=event_type)

        if min_price or max_price:
            #queryset = queryset.annotate(min=Min('ticketclass__price'))

            if min_price:
                queryset = queryset.filter(ticketclasses__price__gte=min_price)
            if max_price:
                queryset = queryset.filter(ticketclasses__price__lte=max_price)
        if queryset:
            serializer = self.get_serializer(queryset.distinct(), many=True)
            return Response(serializer.data)
        return Response("khong co su kien", status=status.HTTP_400_BAD_REQUEST)

# Xoa, Cap nhat nhan xet
from rest_framework.response import Response
from rest_framework import status


class CommentViewSet(viewsets.ViewSet, generics.DestroyAPIView, generics.UpdateAPIView, generics.ListAPIView):
    queryset = Comment.objects.all()
    serializer_class = serializers.CommentSerializer
    permission_classes = [perms.OwnerIsAuthenticated]
    pagination_class = paginators.CommentPaginator

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        response_data = {
            "statusCode": 201,
            "error": None,
            "message": "Update an event",
            "data": {
                "id": instance.id,
                "content": instance.content,
                "Full name": instance.user.get_full_name(),
                "Event's name": instance.event.name,
                "createdAt": instance.created_at.isoformat(),
                "updatedAt": instance.updated_at.isoformat() if instance.updated_at else None,
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        comment = self.get_queryset().filter(pk=pk).first()
        if not comment:
            return Response({
                "statusCode": 404,
                "error": "Comment not found.",
                "message": "Không tìm thấy comment.",
                "data": None,
                "pk": pk
            }, status=status.HTTP_404_NOT_FOUND)

        # Kiểm tra quyền xóa: superuser hoặc chủ comment
        if request.user != comment.user and not request.user.is_superuser:
            return Response({
                "detail": "Bạn không có quyền xóa comment này."
            }, status=status.HTTP_403_FORBIDDEN)

        comment.delete()
        return Response({
            "statusCode": 204,
            "error": None,
            "message": "Comment deleted successfully.",
            "data": None
        }, status=status.HTTP_204_NO_CONTENT)

    def list(self, request, *args, **kwargs):
        # Trả thông tin người dùng đang request
        user = request.user

        if not user.is_authenticated:
            return Response({"detail": "Bạn cần đăng nhập."}, status=status.HTTP_401_UNAUTHORIZED)

        comments = self.get_queryset()

        page = self.paginate_queryset(comments)
        if page is not None:
            serializer = serializers.CommentSerializer(page, many=True)

            page_size = self.paginator.page_size
            current_page = self.paginator.page.number
            total_items = self.paginator.page.paginator.count
            total_pages = self.paginator.page.paginator.num_pages

            return Response({
                "statusCode": 200,
                "error": None,
                "message": "Fetch all comments",
                "data": {
                    "meta": {
                        "page": current_page,
                        "pageSize": page_size,
                        "pages": total_pages,
                        "total": total_items
                    },
                    "result": serializer.data
                }
            },
                status=status.HTTP_200_OK)

        # fallback nếu không phân trang
        serializer = serializers.CommentSerializer(comments, many=True)
        return Response({
            "statusCode": 200,
            "error": None,
            "message": "Fetch all comments",
            "data": {
                "meta": None,
                "result": serializer.data
            }
        })


class UserViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = User.objects.filter(is_active=True).all()
    serializer_class = serializers.UserSerializer
    parser_classes = [parsers.MultiPartParser]
    pagination_class = paginators.EventPaginator

    # permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create']:
            return [permissions.AllowAny()]

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Kiểm tra nếu người dùng không phải owner hoặc admin
        if request.user != instance and not request.user.is_superuser:
            return Response({
                "detail": "Bạn không có quyền chỉnh sửa người dùng này."
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        response_data = {
            "statusCode": 200,
            "error": None,
            "message": "Updated user",
            "data": {
                "user": serializer.data,
                "updatedAt": instance.updated_at.isoformat() if hasattr(instance,
                                                                        'updated_at') and instance.updated_at else None,
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Không tìm thấy người dùng."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_superuser:
            return Response({
                "detail": "Bạn không có quyền chỉnh sửa người dùng này."
            }, status=status.HTTP_403_FORBIDDEN)

        user.delete()
        return Response({
            "statusCode": 204,
            "message": "Xoá người dùng thành công.",
            "data": None
        }, status=status.HTTP_204_NO_CONTENT)

    @action(methods=['get'], url_name='current-user', detail=False)
    def current_user(self, request):
        return Response(serializers.UserSerializer(request.user).data)

    @action(detail=False, methods=['get'], url_path='search')
    def search_users(self, request):
        if not request.user.is_superuser:
            return Response({
                "detail": "Bạn không có quyền tìm kiếm người dùng."
            }, status=status.HTTP_403_FORBIDDEN)

        name = request.query_params.get('name')
        role = request.query_params.get('role')

        users = User.objects.all()

        if name:
            users = users.annotate(
                full_name=Concat('first_name', Value(' '), 'last_name', output_field=CharField())
            ).filter(full_name__icontains=name)

        if role:
            users = users.filter(role__name__iexact=role)

        serializer = serializers.UserSerializer(users, many=True)
        return Response({
            "statusCode": 200,
            "error": None,
            "message": "Danh sách người dùng tìm được.",
            "total": users.count(),
            "data": serializer.data
        })


# Tạo hạng vé cho event (lọc theo id) events/<int:event_id>/add-ticket-class/
class TicketClassViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    queryset = TicketClass.objects.all()
    serializer_class = serializers.TicketClassSerializer
    permission_classes = [perms.IsOrganizer]

    def create(self, request, *args, **kwargs):
        event_id = self.kwargs.get('id')
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return Response({f"'detail': 'Event not found'{event_id}"}, status=status.HTTP_404_NOT_FOUND)

        if (event.user != request.user) and not request.user.is_superuser:
            return Response({
                'statusCode': 403,
                'detail': 'Bạn không phải là người tổ chức sự kiện này.'
            }, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        duplicate_ticket = TicketClass.objects.filter(event=event, name__iexact=name).first()
        if TicketClass.objects.filter(event=event, name__iexact=name).exists():
            return Response({
                'statusCode': 400,
                'error': 'Hạng vé với tên này đã tồn tại cho sự kiện.',
                'event': event.name,
                'duplicate_id': duplicate_ticket.id
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.serializer_class(data=request.data, context={'event': event})

        if serializer.is_valid():
            serializer.save()
            return Response({
                "statusCode": 201,
                "error": None,
                "message": "Tạo hạng vé thành công",
                "user": request.user.get_full_name(),
                "event": event.name,
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        # Kiểm tra nếu người dùng không phải owner hoặc admin
        if request.user != instance.event.user and not request.user.is_superuser:
            return Response({
                "detail": "Bạn không có quyền chỉnh sửa sự kiện này."
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        response_data = {
            "statusCode": 200,
            "error": None,
            "message": "Updated ticketclass",
            "data": {
                "ticket class": serializer.data,
                "updatedAt": instance.updated_at.isoformat() if hasattr(instance,
                                                                        'updated_at') and instance.updated_at else None,
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        try:
            ticketclass = self.get_object()
        except TicketClass.DoesNotExist:
            return Response({"detail": "Không tìm thấy hạng vé."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_superuser:
            return Response({
                "detail": "Bạn không có quyền chỉnh sửa người dùng này."
            }, status=status.HTTP_403_FORBIDDEN)

        ticketclass.delete()
        return Response({
            "statusCode": 204,
            "message": "Xoá hạng vé thành công.",
            "data": None
        }, status=status.HTTP_204_NO_CONTENT)


# Thong bao
class EventReminderViewSet(viewsets.GenericViewSet):
    permission_classes = [perms.IsAdmin]

    @action(methods=['post'], detail=False)
    def send_reminder(self, request):
        today = now()
        target_date = today + timedelta(days=2)

        events = Event.objects.filter(start_time__date=target_date, active=True)
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

        return Response({"message": f"Đã gửi {sent_count} email nhắc nhở thành công. {target_date}"},
                        status=status.HTTP_200_OK)


# Tìm sự kiện theo loại (có sẵn), và theo tên, mô tả (có chứa hoặc gần đúng)
# class EventSearchView(viewsets.ViewSet, generics.ListAPIView):
#     serializer_class = serializers.EventSerializer
#     filter_backends = [DjangoFilterBackend, SearchFilter]
#     filterset_class = filters.EventFilter
#     search_fields = ['name', 'description']
#     permission_classes = [permissions.IsAuthenticated]
#     pagination_class = paginators.EventPaginator
#
#     def get_queryset(self):
#         return Event.objects.filter(active=True)
#
#     def list(self, request):
#         initial_queryset = self.filter_queryset(self.get_queryset())
#
#         # Lấy danh sách event_type xuất hiện trong queryset
#         event_type_ids = initial_queryset.values_list('event_type', flat=True).distinct()
#
#         # Chỉ giữ lại các sự kiện có event_type nằm trong danh sách trên
#         filtered_queryset = initial_queryset.filter(event_type__in=event_type_ids)
#
#         page = self.paginate_queryset(filtered_queryset)
#         if page is not None:
#             serializer = self.get_serializer(page, many=True)
#             return self.get_paginated_response(serializer.data)
#
#         serializer = self.get_serializer(filtered_queryset, many=True)
#         return Response(serializer.data)


# Dat ve
class TicketViewSet(viewsets.ViewSet, generics.CreateAPIView, generics.DestroyAPIView):
    serializer_class = serializers.TicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'check_in':
            return serializers.QRCheckInSerializer
        return serializers.TicketSerializer

    def destroy(self, request, *args, **kwargs):
        ticket_id = kwargs.get("pk")
        ticket = get_object_or_404(Ticket, pk=ticket_id)

        # Tăng lại số lượng vé có thể bán
        ticket_class = ticket.ticket_class
        if ticket_class.event.active:
            ticket_class.total_available += 1
        ticket_class.save()

        ticket.delete()

        return Response({
            "statusCode": 200,
            "message": "Xóa vé thành công",
            "data": None
        }, status=status.HTTP_200_OK)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        user = request.user
        ticket_class = validated_data['ticket_class']
        event = ticket_class.event
        discount_code_str = request.data.get('discount_code')
        price_paid = ticket_class.price  # default
        discount = None

        # Áp dụng mã giảm giá nếu có
        if discount_code_str:
            try:
                discount = DiscountCode.objects.get(code=discount_code_str, valid_from__lte=now(),
                                                    valid_to__gte=now())
            except DiscountCode.DoesNotExist:
                return Response({
                    "statusCode": 400,
                    "error": "Mã giảm giá không hợp lệ hoặc đã hết hạn."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Kiểm tra người dùng đã dùng mã chưa
            if discount.used_by.filter(id=user.id).exists():
                return Response({
                    "statusCode": 400,
                    "error": "Bạn đã sử dụng mã giảm giá này rồi."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Kiểm tra sự kiện
            if discount.events.exists() and event not in discount.events.all():
                return Response({
                    "statusCode": 400,
                    "error": "Mã này không áp dụng cho sự kiện này."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Kiểm tra nhóm
            if not discount.groups.filter(id=user.group.id).exists():
                return Response({
                    "statusCode": 400,
                    "error": "Bạn không thuộc nhóm được áp dụng mã này."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Tính giá sau giảm
            if discount.discount_type.name == 'AMOUNT':
                price_paid = max(price_paid - discount.discount_value, 0)
            else:  # PERCENTAGE
                percentage_discount = price_paid * Decimal(discount.discount_value) / Decimal(100)
                if discount.limit_discount and discount.max_discount_amount:
                    percentage_discount = min(percentage_discount, discount.max_discount_amount)
                price_paid = max(price_paid - percentage_discount, 0)

        # Lưu đơn tạm chờ thanh toán
        payment_log = PaymentLog.objects.create(
            user=user,
            ticket_class=ticket_class,
            amount=price_paid,
            discount_code=discount,
            status='pending',
        )

        # Tạo URL thanh toán VNPay
        vnp = vnpay()
        vnp.requestData['vnp_Version'] = '2.1.0'
        vnp.requestData['vnp_Command'] = 'pay'
        vnp.requestData['vnp_TmnCode'] = settings.VNPAY_TMN_CODE
        vnp.requestData['vnp_Amount'] = int(price_paid * 100)
        vnp.requestData['vnp_CurrCode'] = 'VND'
        vnp.requestData['vnp_TxnRef'] = str(payment_log.id)
        vnp.requestData['vnp_OrderInfo'] = "Thanh toan ve su kien"
        vnp.requestData['vnp_OrderType'] = 'event_ticket'
        vnp.requestData['vnp_Locale'] = 'vn'
        vnp.requestData['vnp_CreateDate'] = datetime.now().strftime('%Y%m%d%H%M%S')
        vnp.requestData['vnp_IpAddr'] = get_client_ip(request)
        vnp.requestData['vnp_ReturnUrl'] = settings.VNPAY_RETURN_URL

        # (Tùy chọn) vnp.requestData['vnp_BankCode'] = 'VNPAYQR'

        vnpay_payment_url = vnp.get_payment_url(settings.VNPAY_PAYMENT_URL, settings.VNPAY_HASH_SECRET_KEY)

        return Response({
            "statusCode": 200,
            "message": "Vui lòng thanh toán qua VNPay.",
            "payment_url": vnpay_payment_url
        })




    # check in
    @action(detail=False, methods=['post'], url_path='check-in')
    def check_in(self, request):
        ticket_code = request.data.get("ticket_code")

        if not ticket_code:
            return Response({"error": "Vui lòng cung cấp mã vé."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            ticket = Ticket.objects.select_related("ticket_class__event", "user").get(ticket_code=ticket_code)
        except Ticket.DoesNotExist:
            return Response({"error": "Mã vé không hợp lệ."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_checked_in:
            return Response({"error": "Vé đã được check-in."}, status=status.HTTP_400_BAD_REQUEST)

        event = ticket.ticket_class.event
        if event.start_time > now():
            return Response(
                f'error: Sự kiện chưa bắt đầu. Ngày bắt đầu sự kiện: {event.start_time}, Ngày hiện tại: {now()}',
                status=status.HTTP_400_BAD_REQUEST)

        # Cập nhật trạng thái check-in
        ticket.is_checked_in = True
        ticket.check_in_time = now()
        ticket.save()

        return Response({
            "message": "Check-in thành công.",
            "ticket_code": ticket.ticket_code,
            "user": ticket.user.get_full_name() or ticket.user.username,
            "event": event.name,
            "ticket_class": ticket.ticket_class.name,
            "check_in_time": ticket.check_in_time,
        }, status=status.HTTP_200_OK)


class VNPayViewSet(viewsets.ViewSet):

    @transaction.atomic
    @action(detail=False, methods=['get'], url_path='vnpay-return')
    def vnpay_return(self, request):
        inputData = request.GET
        if not inputData:
            return render(request, "payment/payment_return.html", {"title": "Kết quả thanh toán", "result": ""})

        # Khởi tạo dữ liệu từ VNPay
        vnp = vnpay()
        vnp.responseData = inputData.dict()
        order_id = inputData.get('vnp_TxnRef')
        amount = int(inputData.get('vnp_Amount', 0)) / 100
        order_desc = inputData.get('vnp_OrderInfo', '')
        vnp_TransactionNo = inputData.get('vnp_TransactionNo', '')
        vnp_ResponseCode = inputData.get('vnp_ResponseCode', '')
        vnp_TmnCode = inputData.get('vnp_TmnCode', '')
        vnp_PayDate = inputData.get('vnp_PayDate', '')
        vnp_BankCode = inputData.get('vnp_BankCode', '')
        vnp_CardType = inputData.get('vnp_CardType', '')

        # Ghi log thanh toán (dù thành công hay thất bại)
        PaymentVNPay.objects.create(
            order_id=order_id,
            amount=amount,
            order_desc=order_desc,
            vnp_TransactionNo=vnp_TransactionNo,
            vnp_ResponseCode=vnp_ResponseCode,
        )

        # Kiểm tra checksum
        if not vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            return render(request, "payment/payment_return.html", {
                "title": "Kết quả thanh toán",
                "result": "Lỗi",
                "order_id": order_id,
                "amount": amount,
                "order_desc": order_desc,
                "vnp_TransactionNo": vnp_TransactionNo,
                "vnp_ResponseCode": vnp_ResponseCode,
                "msg": "Sai checksum"
            })

        if vnp_ResponseCode != "00":
            return render(request, "payment/payment_return.html", {
                "title": "Kết quả thanh toán",
                "result": "Lỗi",
                "order_id": order_id,
                "amount": amount,
                "order_desc": order_desc,
                "vnp_TransactionNo": vnp_TransactionNo,
                "vnp_ResponseCode": vnp_ResponseCode
            })

        # Giao dịch hợp lệ → tạo vé, cập nhật trạng thái
        try:
            with transaction.atomic():
                payment_log = get_object_or_404(PaymentLog, id=order_id, status='pending')
                payment_log.status = 'success'
                payment_log.transaction_id = vnp_TransactionNo
                payment_log.save()

                ticket = Ticket.objects.create(
                    ticket_code=Ticket.generate_ticket_code(payment_log.ticket_class.event),
                    user=payment_log.user,
                    ticket_class=payment_log.ticket_class,
                    price_paid=payment_log.amount
                )

                payment_log.ticket = ticket
                payment_log.save(update_fields=['ticket'])

                user = ticket.user
                event = ticket.ticket_class.event

                if payment_log.discount_code:
                    payment_log.discount_code.used_by.add(user)

                event.update_popularity()
                user.update_group()

                # Gửi email QR
                qr_file_path = serializers.TicketSerializer.create_qr_image(ticket.ticket_code)
                email = EmailMessage(
                    subject=f"[Đặt vé thành công] {event.name}",
                    body=(
                        f"Xin chào {user.get_full_name() or user.username},\n\n"
                        f"Bạn đã đặt vé thành công cho sự kiện: {event.name}.\n"
                        f"Thời gian: {event.start_time.strftime('%H:%M %d/%m/%Y')}\n"
                        f"Mã vé của bạn: {ticket.ticket_code}\n\n"
                        "Hãy đem mã QR đính kèm để check-in tại sự kiện.\n\n"
                        "Cảm ơn bạn đã sử dụng hệ thống!"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user.email],
                )
                with open(qr_file_path, 'rb') as qr_file:
                    email.attach(f'{ticket.ticket_code}.png', qr_file.read(), 'image/png')
                email.send()

        except Exception as e:
            print("Lỗi khi xử lý vé:", e)
            return render(request, "payment/payment_return.html", {
                "title": "Kết quả thanh toán",
                "result": "Lỗi khi xử lý đơn hàng",
                "order_id": order_id,
                "amount": amount,
                "order_desc": order_desc,
                "vnp_TransactionNo": vnp_TransactionNo,
                "vnp_ResponseCode": vnp_ResponseCode
            })

        return render(request, "payment/payment_return.html", {
            "title": "Kết quả thanh toán",
            "result": "Thành công",
            "order_id": order_id,
            "amount": amount,
            "order_desc": order_desc,
            "vnp_TransactionNo": vnp_TransactionNo,
            "vnp_ResponseCode": vnp_ResponseCode,

            "user_full_name": user.get_full_name() or user.username,
    "user_email": user.email,
    "event_name": event.name,
    "event_time": event.start_time.strftime('%H:%M %d/%m/%Y'),
    "ticket_code": ticket.ticket_code,
    "event_location": event.location
        })


class CustomTokenView(TokenView):
    def post(self, request, *args, **kwargs):
        # Gọi logic mặc định để lấy token
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            data = json.loads(response.content)

            user = request.user
            if not user or user.is_anonymous:
                # Với password grant, bạn phải lấy user từ request.POST['username']
                username = request.POST.get('username')
                try:
                    user = User.objects.get(username=username)
                except User.DoesNotExist:
                    user = None

            custom_response = {
                "statusCode": 200,
                "error": None,
                "message": "Login successful",
                "data": {
                    "user": {
                        "id": user.id if user else None,
                        "email": user.email if user else None,
                        "name": user.get_full_name() or user.username if user else None,
                        "role": user.role.name
                    }
                },
                "access_token": data.get("access_token")
            }
            return JsonResponse(custom_response, status=200)

        return response


class DiscountTypeViewSet(viewsets.ModelViewSet):
    queryset = DiscountType.objects.all()
    serializer_class = serializers.DiscountTypeSerializer
    permission_classes = [perms.IsAdmin]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "statusCode": 200,
            "error": None,
            "message": "Danh sách loại mã giảm giá",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "statusCode": 201,
                "error": None,
                "message": "Tạo loại mã giảm giá thành công",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response({
            "statusCode": 400,
            "message": "Tạo loại mã giảm giá thất bại",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "statusCode": 200,
            "message": "Chi tiết loại mã giảm giá",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "statusCode": 200,
                "message": "Cập nhật loại mã giảm giá thành công",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        return Response({
            "message": "Cập nhật loại mã giảm giá thất bại",
            "errors": serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except DiscountType.DoesNotExist:
            return Response({
                "statusCode": 404,
                "error": "Event not found.",
                "message": "Không tìm thấy sự kiện.",
                "data": None,
            }, status=status.HTTP_404_NOT_FOUND)

        instance.delete()
        return Response({
            "statusCode": 200,
            "message": "Xóa loại mã giảm giá thành công",
            "data": None
        }, status=status.HTTP_204_NO_CONTENT)


class DiscountCodeViewSet(viewsets.ViewSet, generics.CreateAPIView):
    queryset = DiscountCode.objects.all()
    serializer_class = serializers.DiscountCodeSerializer
    permission_classes = [perms.IsAdmin]

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        # Nếu không gửi field events hoặc gửi rỗng thì tự động thêm tất cả sự kiện
        if not data.get("events"):
            all_event_ids = list(Event.objects.values_list('id', flat=True))
            data['events'] = all_event_ids

        if not data.get("groups"):
            all_groups_ids = list(CustomerGroup.objects.values_list('id', flat=True))
            data['groups'] = all_groups_ids

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response({
            "statusCode": 201,
            "error": None,
            "message": "Tạo mã giảm giá thành công",
            "user": request.user.id,
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)


            # Thống kê bình luận theo năm




class ReportViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_filtered_events(self, user):
        if user.role.id == 1:  # Admin
            return Event.objects.all()
        elif user.role.id == 2:  # Organizer
            return Event.objects.filter(organizer=user)
        return Event.objects.none()

    @action(detail=False, methods=['get'], url_path='monthly')
    def report_by_month(self, request):
        try:
            year = int(request.query_params.get('year'))
            month = int(request.query_params.get('month'))
        except (TypeError, ValueError):
            return Response({"error": "Vui lòng cung cấp đúng định dạng ?year=YYYY&month=MM"}, status=400)

        user = request.user
        events = self.get_filtered_events(user).filter(start_time__year=year, start_time__month=month)

        data = []

        for event in events:
            ticket_count = Ticket.objects.filter(
                ticket_class__event=event,
                booked_at__year=year,
                booked_at__month=month
            ).count()

            revenue_sum = Ticket.objects.filter(
                ticket_class__event=event,
                booked_at__year=year,
                booked_at__month=month
            ).aggregate(total=Sum('price_paid'))['total'] or 0

            comment_count = Comment.objects.filter(
                event=event,
                created_at__year=year,
                created_at__month=month
            ).count()

            data.append({
                'event_id': event.id,
                'event_name': event.name,
                'total_tickets': ticket_count,
                'total_revenue': revenue_sum,
                'total_comments': comment_count
            })

        return Response({
            "year": year,
            "month": month,
            "total_event": events.count(),
            "event_statistics": data
        })

    @action(detail=False, methods=['get'], url_path='yearly')
    def report_by_year(self, request):
        try:
            year = int(request.query_params.get('year'))
        except (TypeError, ValueError):
            return Response({"error": "Vui lòng cung cấp đúng định dạng ?year=YYYY"}, status=400)

        user = request.user
        events = self.get_filtered_events(user).filter(start_time__year=year)

        data = []

        for event in events:
            ticket_count = Ticket.objects.filter(
                ticket_class__event=event,
                booked_at__year=year
            ).count()

            revenue_sum = Ticket.objects.filter(
                ticket_class__event=event,
                booked_at__year=year
            ).aggregate(total=Sum('price_paid'))['total'] or 0

            comment_count = Comment.objects.filter(
                event=event,
                created_at__year=year
            ).count()

            data.append({
                'event_id': event.id,
                'event_name': event.name,
                'total_tickets': ticket_count,
                'total_revenue': revenue_sum,
                'total_comments': comment_count
            })

        return Response({
            "year": year,
            "total_event": events.count(),
            "event_statistics": data
        })


#Thanh toan VNPay


def index(request):
    return render(request, "payment/index.html", {"title": "Danh sách demo"})


def hmacsha512(key, data):
    byteKey = key.encode('utf-8')
    byteData = data.encode('utf-8')
    return hmac.new(byteKey, byteData, hashlib.sha512).hexdigest()


def payment(request):

    if request.method == 'POST':
        # Process input data and build url payment
        form = PaymentForm(request.POST)
        if form.is_valid():
            order_type = form.cleaned_data['order_type']
            order_id = form.cleaned_data['order_id']
            amount = form.cleaned_data['amount']
            order_desc = form.cleaned_data['order_desc']
            bank_code = form.cleaned_data['bank_code']
            language = form.cleaned_data['language']
            ipaddr = get_client_ip(request)
            # Build URL Payment
            vnp = vnpay()
            vnp.requestData['vnp_Version'] = '2.1.0'
            vnp.requestData['vnp_Command'] = 'pay'
            vnp.requestData['vnp_TmnCode'] = settings.VNPAY_TMN_CODE
            vnp.requestData['vnp_Amount'] = amount * 100
            vnp.requestData['vnp_CurrCode'] = 'VND'
            vnp.requestData['vnp_TxnRef'] = order_id
            vnp.requestData['vnp_OrderInfo'] = order_desc
            vnp.requestData['vnp_OrderType'] = order_type
            # Check language, default: vn
            if language and language != '':
                vnp.requestData['vnp_Locale'] = language
            else:
                vnp.requestData['vnp_Locale'] = 'vn'
                # Check bank_code, if bank_code is empty, customer will be selected bank on VNPAY
            if bank_code and bank_code != "":
                vnp.requestData['vnp_BankCode'] = bank_code

            vnp.requestData['vnp_CreateDate'] = datetime.now().strftime('%Y%m%d%H%M%S')  # 20150410063022
            vnp.requestData['vnp_IpAddr'] = ipaddr
            vnp.requestData['vnp_ReturnUrl'] = settings.VNPAY_RETURN_URL
            vnpay_payment_url = vnp.get_payment_url(settings.VNPAY_PAYMENT_URL, settings.VNPAY_HASH_SECRET_KEY)
            print(vnpay_payment_url)
            return redirect(vnpay_payment_url)
        else:
            print("Form input not validate")
    else:
        return render(request, "payment/payment.html", {"title": "Thanh toán"})


def payment_ipn(request):
    inputData = request.GET
    if inputData:
        vnp = vnpay()
        vnp.responseData = inputData.dict()
        order_id = inputData['vnp_TxnRef']
        amount = inputData['vnp_Amount']
        order_desc = inputData['vnp_OrderInfo']
        vnp_TransactionNo = inputData['vnp_TransactionNo']
        vnp_ResponseCode = inputData['vnp_ResponseCode']
        vnp_TmnCode = inputData['vnp_TmnCode']
        vnp_PayDate = inputData['vnp_PayDate']
        vnp_BankCode = inputData['vnp_BankCode']
        vnp_CardType = inputData['vnp_CardType']
        if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            # Check & Update Order Status in your Database
            # Your code here
            firstTimeUpdate = True
            totalamount = True
            if totalamount:
                if firstTimeUpdate:
                    if vnp_ResponseCode == '00':
                        print('Payment Success. Your code implement here')
                    else:
                        print('Payment Error. Your code implement here')

                    # Return VNPAY: Merchant update success
                    result = JsonResponse({'RspCode': '00', 'Message': 'Confirm Success'})
                else:
                    # Already Update
                    result = JsonResponse({'RspCode': '02', 'Message': 'Order Already Update'})
            else:
                # invalid amount
                result = JsonResponse({'RspCode': '04', 'Message': 'invalid amount'})
        else:
            # Invalid Signature
            result = JsonResponse({'RspCode': '97', 'Message': 'Invalid Signature'})
    else:
        result = JsonResponse({'RspCode': '99', 'Message': 'Invalid request'})

    return result


def payment_return(request):
    inputData = request.GET
    if inputData:
        vnp = vnpay()
        vnp.responseData = inputData.dict()
        order_id = inputData['vnp_TxnRef']
        amount = int(inputData['vnp_Amount']) / 100
        order_desc = inputData['vnp_OrderInfo']
        vnp_TransactionNo = inputData['vnp_TransactionNo']
        vnp_ResponseCode = inputData['vnp_ResponseCode']
        vnp_TmnCode = inputData['vnp_TmnCode']
        vnp_PayDate = inputData['vnp_PayDate']
        vnp_BankCode = inputData['vnp_BankCode']
        vnp_CardType = inputData['vnp_CardType']

        payment = PaymentVNPay.objects.create(
            order_id = order_id,
            amount = amount,
            order_desc = order_desc ,
            vnp_TransactionNo = vnp_TransactionNo,
            vnp_ResponseCode = vnp_ResponseCode
        )

        if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            if vnp_ResponseCode == "00":
                return render(request, "payment/payment_return.html", {"title": "Kết quả thanh toán",
                                                               "result": "Thành công", "order_id": order_id,
                                                               "amount": amount,
                                                               "order_desc": order_desc,
                                                               "vnp_TransactionNo": vnp_TransactionNo,
                                                               "vnp_ResponseCode": vnp_ResponseCode})
            else:
                return render(request, "payment/payment_return.html", {"title": "Kết quả thanh toán",
                                                               "result": "Lỗi", "order_id": order_id,
                                                               "amount": amount,
                                                               "order_desc": order_desc,
                                                               "vnp_TransactionNo": vnp_TransactionNo,
                                                               "vnp_ResponseCode": vnp_ResponseCode})
        else:
            return render(request, "payment/payment_return.html",
                          {"title": "Kết quả thanh toán", "result": "Lỗi", "order_id": order_id, "amount": amount,
                           "order_desc": order_desc, "vnp_TransactionNo": vnp_TransactionNo,
                           "vnp_ResponseCode": vnp_ResponseCode, "msg": "Sai checksum"})
    else:
        return render(request, "payment/payment_return.html", {"title": "Kết quả thanh toán", "result": ""})


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

n = random.randint(10**11, 10**12 - 1)
n_str = str(n)
while len(n_str) < 12:
    n_str = '0' + n_str


def query(request):
    if request.method == 'GET':
        return render(request, "payment/query.html", {"title": "Kiểm tra kết quả giao dịch"})

    url = settings.VNPAY_API_URL
    secret_key = settings.VNPAY_HASH_SECRET_KEY
    vnp_TmnCode = settings.VNPAY_TMN_CODE
    vnp_Version = '2.1.0'

    vnp_RequestId = n_str
    vnp_Command = 'querydr'
    vnp_TxnRef = request.POST['order_id']
    vnp_OrderInfo = 'kiem tra gd'
    vnp_TransactionDate = request.POST['trans_date']
    vnp_CreateDate = datetime.now().strftime('%Y%m%d%H%M%S')
    vnp_IpAddr = get_client_ip(request)

    hash_data = "|".join([
        vnp_RequestId, vnp_Version, vnp_Command, vnp_TmnCode,
        vnp_TxnRef, vnp_TransactionDate, vnp_CreateDate,
        vnp_IpAddr, vnp_OrderInfo
    ])

    secure_hash = hmac.new(secret_key.encode(), hash_data.encode(), hashlib.sha512).hexdigest()

    data = {
        "vnp_RequestId": vnp_RequestId,
        "vnp_TmnCode": vnp_TmnCode,
        "vnp_Command": vnp_Command,
        "vnp_TxnRef": vnp_TxnRef,
        "vnp_OrderInfo": vnp_OrderInfo,
        "vnp_TransactionDate": vnp_TransactionDate,
        "vnp_CreateDate": vnp_CreateDate,
        "vnp_IpAddr": vnp_IpAddr,
        "vnp_Version": vnp_Version,
        "vnp_SecureHash": secure_hash
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        response_json = json.loads(response.text)
    else:
        response_json = {"error": f"Request failed with status code: {response.status_code}"}

    return render(request, "payment/query.html", {"title": "Kiểm tra kết quả giao dịch", "response_json": response_json})

def refund(request):
    if request.method == 'GET':
        return render(request, "payment/refund.html", {"title": "Hoàn tiền giao dịch"})

    url = settings.VNPAY_API_URL
    secret_key = settings.VNPAY_HASH_SECRET_KEY
    vnp_TmnCode = settings.VNPAY_TMN_CODE
    vnp_RequestId = n_str
    vnp_Version = '2.1.0'
    vnp_Command = 'refund'
    vnp_TransactionType = request.POST['TransactionType']
    vnp_TxnRef = request.POST['order_id']
    vnp_Amount = request.POST['amount']
    vnp_OrderInfo = request.POST['order_desc']
    vnp_TransactionNo = '0'
    vnp_TransactionDate = request.POST['trans_date']
    vnp_CreateDate = datetime.now().strftime('%Y%m%d%H%M%S')
    vnp_CreateBy = 'user01'
    vnp_IpAddr = get_client_ip(request)

    hash_data = "|".join([
        vnp_RequestId, vnp_Version, vnp_Command, vnp_TmnCode, vnp_TransactionType, vnp_TxnRef,
        vnp_Amount, vnp_TransactionNo, vnp_TransactionDate, vnp_CreateBy, vnp_CreateDate,
        vnp_IpAddr, vnp_OrderInfo
    ])

    secure_hash = hmac.new(secret_key.encode(), hash_data.encode(), hashlib.sha512).hexdigest()

    data = {
        "vnp_RequestId": vnp_RequestId,
        "vnp_TmnCode": vnp_TmnCode,
        "vnp_Command": vnp_Command,
        "vnp_TxnRef": vnp_TxnRef,
        "vnp_Amount": vnp_Amount,
        "vnp_OrderInfo": vnp_OrderInfo,
        "vnp_TransactionDate": vnp_TransactionDate,
        "vnp_CreateDate": vnp_CreateDate,
        "vnp_IpAddr": vnp_IpAddr,
        "vnp_TransactionType": vnp_TransactionType,
        "vnp_TransactionNo": vnp_TransactionNo,
        "vnp_CreateBy": vnp_CreateBy,
        "vnp_Version": vnp_Version,
        "vnp_SecureHash": secure_hash
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        response_json = json.loads(response.text)
    else:
        response_json = {"error": f"Request failed with status code: {response.status_code}"}

    return render(request, "payment/refund.html", {"title": "Kết quả hoàn tiền giao dịch", "response_json": response_json})