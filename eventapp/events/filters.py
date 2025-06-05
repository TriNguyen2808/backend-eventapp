from django_filters import rest_framework as filters
from .models import Event

class EventFilter(filters.FilterSet):
    event_type = filters.CharFilter(field_name='event_type__name', lookup_expr='iexact')

    class Meta:
        model = Event
        fields = ['event_type']
