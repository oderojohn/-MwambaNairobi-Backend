from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'carts', views.CartViewSet)
router.register(r'cart-items', views.CartItemViewSet)
router.register(r'sales', views.SaleViewSet)
router.register(r'sale-items', views.SaleItemViewSet)
router.register(r'invoices', views.InvoiceViewSet)
router.register(r'invoice-items', views.InvoiceItemViewSet)
router.register(r'audit-logs', views.AuditLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # Returns endpoints - explicit paths to avoid double-prefix issue
    path('returns/', views.ReturnViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('returns/<int:pk>/', views.ReturnViewSet.as_view({'get': 'retrieve', 'put': 'update', 'delete': 'destroy'})),
]
