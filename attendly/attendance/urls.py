from django.urls import path
from . import views

urlpatterns = [
    path('scanner/', views.scanner_page, name='scanner_page'),
    path('qr-scan/', views.qr_scan, name='qr_scan'),
    path('api/qr-attendance/', views.auto_attendance_punch, name='auto_attendance_punch'),
]