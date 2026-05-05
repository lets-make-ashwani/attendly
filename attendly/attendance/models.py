from django.db import models
from django.conf import settings
from django.utils import timezone

class Attendance(models.Model):
    # 🚨 related_name required for admin_dashboard queries
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField(default=timezone.localdate) # 🌍 Prevents UTC-midnight date shifts
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        # 🛡️ Prevents race-condition double check-ins at the database level
        constraints = [models.UniqueConstraint(fields=['user', 'date'], name='unique_daily_attendance')]

    def __str__(self):
        return f"{self.user.username} - {self.date}"