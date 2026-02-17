from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet)
router.register(r'journal-entries', views.JournalEntryViewSet)
router.register(r'recurring-expenses', views.RecurringExpenseViewSet)
router.register(r'automatic-rules', views.AutomaticEntryRuleViewSet)
router.register(r'reports', views.ReportsViewSet, basename='reports')

urlpatterns = [
    path('', include(router.urls)),
]
