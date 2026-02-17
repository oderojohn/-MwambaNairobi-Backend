from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ETimsConfigurationViewSet,
    FiscalReceiptViewSet,
    OfflineTransactionQueueViewSet,
    ETimsApiLogViewSet,
    ETimsStatusViewSet
)

router = DefaultRouter()
router.register(r'config', ETimsConfigurationViewSet, basename='etims-config')
router.register(r'receipts', FiscalReceiptViewSet, basename='etims-receipts')
router.register(r'offline', OfflineTransactionQueueViewSet, basename='etims-offline')
router.register(r'logs', ETimsApiLogViewSet, basename='etims-logs')
router.register(r'status', ETimsStatusViewSet, basename='etims-status')

urlpatterns = [
    path('', include(router.urls)),
]
