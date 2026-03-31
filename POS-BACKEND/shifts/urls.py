from django.urls import path
from . import views

urlpatterns = [
    path('', views.ShiftViewSet.as_view({'get': 'list'})),
    path('current/', views.CurrentShiftView.as_view()),
    path('start/', views.StartShiftView.as_view()),
    path('end/', views.EndShiftView.as_view()),
    path('end-test/', views.EndShiftTestView.as_view()),
    path('all/', views.AllShiftsView.as_view()),
    path('<int:shift_id>/reopen/', views.AdminShiftManagementView.as_view(), {'action': 'reopen'}),
    path('<int:shift_id>/force_close/', views.AdminShiftManagementView.as_view(), {'action': 'force_close'}),
]
