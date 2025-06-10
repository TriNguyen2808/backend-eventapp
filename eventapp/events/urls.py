from django.contrib import admin
from django.urls import path, include
from rest_framework import routers
from . import views
from oauth2_provider.views import TokenView, RevokeTokenView


routers = routers.DefaultRouter()
routers.register('events', views.EventViewSet, basename='events')
routers.register('users', views.UserViewSet, basename='users')
routers.register('comments', views.CommentViewSet, basename='comments')
routers.register('reminders', views.EventReminderViewSet, basename='reminders')
routers.register('tickets', views.TicketViewSet, basename='tickets')
routers.register('ticketclasses', views.TicketClassViewSet, basename='ticketclasses')
routers.register('discountcodes', views.DiscountCodeViewSet, basename='discountcodes')
routers.register('discounttypes', views.DiscountTypeViewSet, basename='discounttypes')
routers.register('reports', views.ReportViewSet, basename='reports')
routers.register('payments', views.VNPayViewSet, basename='vnpay')


urlpatterns = [
    path('',include(routers.urls)),
    #path("o/token/", views.CustomTokenView.as_view(), name="custom_token"),
    path('events/<int:id>/ticketclass/', views.TicketClassViewSet.as_view({'post': 'create'})),
    #path('events/search/', views.EventSearchView.as_view({'get': 'list'})),
    path('accounts/', include('allauth.urls')),
    path('login/', views.CustomTokenView.as_view(), name='token'),
    path('logout/', RevokeTokenView.as_view(), name='revoke-token'),
    # path('momo/init/', views.MomoPaymentInitView.as_view()),
    # path('momo/callback/', views.MomoCallbackView.as_view()),
]

#http://localhost:8000/accounts/login/