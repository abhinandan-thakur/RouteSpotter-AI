from django.urls import path
from .views import route_plan

urlpatterns = [
    path("v1/", route_plan, name="route-plan"),
]