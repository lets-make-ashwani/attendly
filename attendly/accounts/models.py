import datetime
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_admin', True)  # Automatically grant Admin Dashboard access
        extra_fields.setdefault('is_approved', True) # Auto-approve admins

        return super().create_superuser(username, email, password, **extra_fields)

class User(AbstractUser):
    is_employee = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    
    mobile_no = models.CharField(max_length=15, blank=True, default="")
    is_approved = models.BooleanField(default=False) # Requires Admin approval

    # Profile & Shift features
    department = models.CharField(max_length=100, blank=True, default="")
    designation = models.CharField(max_length=100, blank=True, default="")
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    shift_start = models.TimeField(default=datetime.time(9, 0)) # Default 9:00 AM
    shift_end = models.TimeField(default=datetime.time(17, 0)) # Default 5:00 PM

    objects = CustomUserManager()

class OfficeLocation(models.Model):
    latitude = models.FloatField(default=28.6139)
    longitude = models.FloatField(default=77.2090)
    radius = models.IntegerField(default=100) # Geofence radius

    def save(self, *args, **kwargs):
        self.pk = 1  # Ensure only one record exists at a time
        super().save(*args, **kwargs)

class LeaveRequest(models.Model):
    LEAVE_TYPES = (
        ('Sick', 'Sick Leave'),
        ('Vacation', 'Vacation'),
        ('Half-Day', 'Half Day'),
    )
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='leaves')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 🛡️ Prevents an employee from double-submitting identical leave requests
        constraints = [models.UniqueConstraint(fields=['user', 'start_date', 'end_date'], name='unique_leave_request')]