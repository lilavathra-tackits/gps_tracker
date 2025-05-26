from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('devices/', views.device_list, name='device_list'),
    path('devices/add/', views.add_device, name='add_device'),
    path('devices/<str:device_id>/login/', views.device_login, name='device_login'),
    path('devices/<str:device_id>/dashboard/', views.dashboard, name='dashboard'),
    path('devices/<str:device_id>/data/', views.save_device_data, name='save_device_data'),
    path('devices/<str:device_id>/history/', views.device_history, name='device_history'),
    path('devices/<str:device_id>/history-data/', views.device_history_data, name='device_history_data'),
    path('devices/<str:device_id>/device-data/', views.device_data, name='device_data'),
    path('devices/<str:device_id>/share/', views.share_device, name='share_device'),
    path('devices/<str:device_id>/share/<int:share_id>/modify/', views.modify_share, name='modify_share'),
    path('devices/<str:device_id>/maintenance/', views.maintenance_status, name='maintenance_status'),
    path('devices/<str:device_id>/edit/', views.edit_device, name='edit_device'),
    path('devices/notifications/', views.notifications, name='notifications'),
    path('devices/notifications/<int:notification_id>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('settings/', views.user_settings, name='user_settings'),
]