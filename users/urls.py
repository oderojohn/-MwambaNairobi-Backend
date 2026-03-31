from django.urls import include, path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.UserProfileViewSet, basename='user')
router.register(r'topbar-permissions', views.TopBarPermissionViewSet, basename='topbar-permissions')

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', views.RefreshView.as_view(), name='refresh'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('me/', views.CurrentUserView.as_view(), name='current-user'),
    path('roles/', views.RoleListView.as_view(), name='roles'),
    path('groups/', views.GroupListCreateView.as_view(), name='groups'),
    path('groups/<int:pk>/', views.GroupDetailView.as_view(), name='group-detail'),
    path('', include(router.urls)),
    path('users/', include(router.urls)),
]
