from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),

    path('dashboard/', views.employee_dashboard, name='dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    path('employees/', views.employee_list, name='employees'),
    path('attendance/', views.attendance_page, name='attendance'),
    path('reports/', views.reports_page, name='reports'),
    path('employee/<int:emp_id>/', views.employee_detail, name='employee_detail'),
    path('employee/<int:emp_id>/edit/', views.edit_employee, name='edit_employee'),
    
    path('approve/<int:user_id>/', views.approve_user, name='approve_user'),
    path('delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('update-location/', views.update_location, name='update_location'),

    path('update-profile/', views.update_profile, name='update_profile'),
    path('request-leave/', views.request_leave, name='request_leave'),
    path('approve-leave/<int:leave_id>/', views.approve_leave, name='approve_leave'),
    path('reject-leave/<int:leave_id>/', views.reject_leave, name='reject_leave'),
    path('export-csv/', views.export_attendance_csv, name='export_attendance_csv'),
    path('qr-generator/', views.qr_generator, name='qr_generator'),

    path('logout/', views.logout_view, name='logout'),

    # Password Reset URLs
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='password_reset.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='password_reset_confirm.html'), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='password_reset_complete.html'), name='password_reset_complete'),
]