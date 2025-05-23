from django.urls import path
from . import views

urlpatterns = [
    path('', views.device_list, name='device_list'),
    path('add/', views.add_device, name='add_device'),
    path('<str:device_id>/login/', views.device_login, name='device_login'),
    path('<str:device_id>/dashboard/', views.dashboard, name='dashboard'),
    path('devices/<str:device_id>/save-data/', views.save_device_data, name='save_device_data'),
    path('device/<str:device_id>/history/', views.device_history, name='device_history'),
    path('device/<str:device_id>/history-data/', views.device_history_data, name='device_history_data'),
    path('devices/<str:device_id>/data/', views.device_data, name='device_data'),
    path('<str:device_id>/share/', views.share_device, name='share_device'),
    path('<str:device_id>/share/<int:share_id>/modify/', views.modify_share, name='modify_share'),
    path('<str:device_id>/maintenance/', views.maintenance_status, name='maintenance_status'),
    path('<str:device_id>/edit/', views.edit_device, name='edit_device'),
    path('<str:device_id>/share-edit/', views.share_edit_device, name='share_edit_device'),
    path('notifications/', views.notifications, name='notifications'),
    path('settings/', views.user_settings, name='user_settings'),
]