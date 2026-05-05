from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, OfficeLocation, LeaveRequest

class CustomUserAdmin(UserAdmin):
    # Add your custom fields to the admin form
    fieldsets = UserAdmin.fieldsets + (
        ('Employee & HR Details', {
            'fields': ('mobile_no', 'department', 'designation', 'shift_start', 'shift_end', 'profile_picture', 'is_employee', 'is_admin', 'is_approved')
        }),
    )

# Register models to the Django Admin Panel
admin.site.register(User, CustomUserAdmin)
admin.site.register(OfficeLocation)
admin.site.register(LeaveRequest)