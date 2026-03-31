from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.CustomerViewSet, basename='customer')

urlpatterns = [
    path('<int:customer_pk>/loyalty/', views.LoyaltyView.as_view()),
    path('lookup/', views.CustomerLookupView.as_view(), name='customer-lookup'),
    path('', include(router.urls)),
]
