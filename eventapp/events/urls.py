from django.contrib import admin
from django.urls import path, include
from rest_framework import routers
from . import views

routers = routers.DefaultRouter()
routers.register('events', views.EventViewSet, basename='events')
routers.register('users', views.UserViewSet, basename='users')
routers.register('comments', views.CommentViewSet, basename='comments')
routers.register('reminders', views.EventReminderViewSet, basename='reminders')
routers.register('tickets', views.TicketViewSet, basename='tickets')
routers.register('ticketclasses', views.TicketClassViewSet, basename='ticketclasses')

urlpatterns = [
    path('',include(routers.urls)),
    path("o/token/", views.CustomTokenView.as_view(), name="custom_token"),
    path('events/<int:id>/ticketclass/', views.TicketClassViewSet.as_view({'post': 'create'})),
    path('events/search/', views.EventSearchView.as_view({'get': 'list'})),
    path('accounts/', include('allauth.urls')),
    # path('momo/init/', views.MomoPaymentInitView.as_view()),
    # path('momo/callback/', views.MomoCallbackView.as_view()),
]

#http://localhost:8000/accounts/login/