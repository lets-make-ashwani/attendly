import json
import csv
import qrcode
import base64
import threading
from datetime import timedelta, datetime
from io import BytesIO
from django.http import HttpResponse
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Count, Q
from django.db import IntegrityError
from django.core.signing import TimestampSigner

from .models import User, OfficeLocation, LeaveRequest
from attendance.models import Attendance


# 🛡️ Helper to safely extract time from mixed Database artifacts (prevents 500 Server Errors)
def _extract_time(dt_obj):
    if not dt_obj: return None
    if hasattr(dt_obj, 'astimezone'): return timezone.localtime(dt_obj).time() # New DateTimeField
    if hasattr(dt_obj, 'time'): return dt_obj.time() # Old TimeField artifact
    if isinstance(dt_obj, str): # SQLite string artifact
        try: return datetime.strptime(dt_obj.split('.')[0], '%H:%M:%S').time()
        except ValueError: pass
    return dt_obj


#  Helper to send emails in the background to prevent server timeouts (500 Errors)
def send_email_async(subject, message, from_email, recipient_list):
    valid_emails = [e for e in recipient_list if e]
    if valid_emails:
        threading.Thread(
            target=send_mail, 
            args=(subject, message, from_email, valid_emails), 
            kwargs={'fail_silently': True}
        ).start()


# 🔐 LOGIN VIEW
def login_view(request):
    next_url = request.GET.get('next') or request.POST.get('next')
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            return render(request, 'login.html', {'error': 'Please provide both username and password', 'next': next_url})

        user = authenticate(request, username=username, password=password)

        if user:
            # Block unapproved users
            if not user.is_approved and not user.is_admin:
                return render(request, 'login.html', {'error': 'Account pending Admin approval.', 'next': next_url})

            login(request, user)
            if next_url:
                return redirect(next_url)
            return redirect('admin_dashboard' if user.is_admin else 'dashboard')

        return render(request, 'login.html', {'error': 'Invalid credentials', 'next': next_url})

    return render(request, 'login.html', {'next': next_url})


# 📝 REGISTER VIEW (ONBOARDING)
def register_view(request):
    next_url = request.GET.get('next') or request.POST.get('next')
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        mobile_no = request.POST.get('mobile_no')
        
        if not username or not email or not password or not first_name:
            return render(request, 'register.html', {'error': 'Please fill all required fields.', 'next': next_url})
        
        try:
            user = User.objects.create_user(username=username, email=email, password=password)
        except IntegrityError: # 🛡️ Safe concurrency handling
            return render(request, 'register.html', {'error': 'Username already taken.', 'next': next_url})

        user.first_name = first_name
        user.last_name = last_name
        user.mobile_no = mobile_no
        user.save() # is_approved defaults to False

        # 📧 Send alert to all Admins
        admin_emails = list(User.objects.filter(is_admin=True).values_list('email', flat=True))
        send_email_async(
            'New Employee Registration Pending',
            f'A new user ({first_name} {last_name} - {username}) has registered and is waiting for your approval in the dashboard.',
            'system@attendly.com',
            admin_emails
        )
            
        # 📧 Send confirmation to the New User
        send_email_async(
            'Registration Received - Pending Approval',
            f'Hi {first_name},\n\nThank you for registering with Attendly. Your account is currently pending Admin approval. You will receive another email once you are approved to log in.',
            'system@attendly.com',
            [email]
        )

        if next_url:
            return redirect(f'/?next={next_url}')
        return redirect('login')

    return render(request, 'register.html', {'next': next_url})


# 🚪 LOGOUT
def logout_view(request):
    logout(request)
    return redirect('login')


# 👤 EMPLOYEE DASHBOARD (FINAL)
@login_required(login_url='login')
def employee_dashboard(request):
    # Route Admins correctly if they log in via Google
    if request.user.is_admin:
        return redirect('admin_dashboard')
        
    # Block unapproved users if they log in via Google
    if not request.user.is_approved:
        return render(request, 'login.html', {'error': 'Your account is pending Admin approval.'})

    today = timezone.localtime().date()

    record = Attendance.objects.filter(
        user=request.user, date=today
    ).first()

    records = Attendance.objects.filter(user=request.user).order_by('-date')[:30] # Limit history for performance
    
    for r in records:
        r.is_late = r.check_in and request.user.shift_start and _extract_time(r.check_in) > request.user.shift_start
        r.is_early = r.check_out and request.user.shift_end and _extract_time(r.check_out) < request.user.shift_end
    if record:
        record.is_late = record.check_in and request.user.shift_start and _extract_time(record.check_in) > request.user.shift_start
        record.is_early = record.check_out and request.user.shift_end and _extract_time(record.check_out) < request.user.shift_end
        
    leaves = LeaveRequest.objects.filter(user=request.user).order_by('-created_at')[:15] # Limit list for performance
    
    # 📅 Prepare Calendar Events for Employee
    events = []
    for r in records:
        if getattr(r, 'is_late', False):
            title, color = 'Late', '#dc3545'
        elif getattr(r, 'is_early', False):
            title, color = 'Early Out', '#fd7e14'
        else:
            title, color = 'Present', '#28a745'
            
        events.append({
            'title': f'{title}',
            'start': r.date.strftime('%Y-%m-%d'),
            'color': color
        })
        
    # 🛡️ Separate query for calendar to prevent "Cannot filter a query once a slice has been taken" TypeError
    thirty_days_ago = today - timedelta(days=30)
    approved_leaves = LeaveRequest.objects.filter(user=request.user, status='Approved', end_date__gte=thirty_days_ago)
    for l in approved_leaves:
        events.append({
            'title': f'Leave ({l.leave_type})',
            'start': l.start_date.strftime('%Y-%m-%d'),
            'end': (l.end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
            'color': '#ffc107',
            'textColor': '#000'
        })

    return render(request, 'employee_dashboard.html', {
        'record': record,   # today
        'records': records, # history
        'leaves': leaves,
        'calendar_events': events
    })


# 🛠️ ADMIN DASHBOARD
@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def admin_dashboard(request):
    today = timezone.localtime().date()

    # Optimized queries for performance
    stats = User.objects.filter(is_employee=True).aggregate(
        total_employees=Count('id'),
        present_count=Count('id', filter=Q(attendance__date=today, attendance__check_in__isnull=False))
    )
    attendance_today = Attendance.objects.filter(date=today)

    # Fetch pending user applications
    pending_users = User.objects.filter(is_approved=False, is_admin=False)
    pending_leaves = LeaveRequest.objects.filter(status='Pending')

    # Calculate variables for dashboard
    total = stats['total_employees'] or 0
    present = stats['present_count'] or 0
    absent = total - present
    progress_percentage = int((present / total) * 100) if total > 0 else 0

    # Fetch or create the active office location for the form
    location, _ = OfficeLocation.objects.get_or_create(pk=1)

    # 📅 Prepare Calendar Events for Admin
    admin_events = []
    
    # Add approved leaves to calendar (🛡️ Bound memory by last 30 days and future leaves)
    thirty_days_ago = today - timedelta(days=30)
    approved_leaves = LeaveRequest.objects.filter(status='Approved', end_date__gte=thirty_days_ago).select_related('user')
    for l in approved_leaves:
        admin_events.append({
            'title': f"{l.user.get_full_name() or l.user.username} (Leave)",
            'start': l.start_date.strftime('%Y-%m-%d'),
            'end': (l.end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
            'color': '#17a2b8'
        })
    # Add daily presence count to calendar (Limited to 30 days to prevent full table scan)
    thirty_days_ago = today - timedelta(days=30)
    daily_attendance = Attendance.objects.filter(date__gte=thirty_days_ago).values('date').annotate(present_count=Count('id'))
    for d in daily_attendance:
        admin_events.append({
            'title': f"{d['present_count']} Present",
            'start': d['date'].strftime('%Y-%m-%d'),
            'color': '#28a745'
        })

    context = {
        'total_employees': total,
        'present_count': present,
        'absent_count': absent,
        'progress_percentage': progress_percentage,
        'attendance_list': attendance_today.select_related('user'),
        'pending_users': pending_users,
        'location': location,
        'pending_leaves': pending_leaves,
        'calendar_events': admin_events
    }

    return render(request, 'admin_dashboard.html', context)

# ✅ APPROVE USER
@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def approve_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_approved = True
    user.is_employee = True
    user.save()
    send_email_async(
        'Account Approved',
        'Your Attendly account has been approved! You can now log in.',
        'admin@attendly.com',
        [user.email]
    )
    return redirect('admin_dashboard')

# ❌ REJECT/DELETE USER
@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    was_approved = user.is_approved
    if not user.is_admin: # Protect admins from being deleted easily
        user.delete()
    return redirect('employees' if was_approved else 'admin_dashboard')


# 📍 UPDATE OFFICE LOCATION
@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
@require_POST
def update_location(request):
    try:
        lat = request.POST.get('latitude')
        lon = request.POST.get('longitude')
        rad = request.POST.get('radius')
        loc, _ = OfficeLocation.objects.get_or_create(pk=1)
        loc.latitude = float(lat)
        loc.longitude = float(lon)
        if rad:
            loc.radius = int(rad)
        loc.save()
    except (ValueError, TypeError):
        pass # Gracefully handle invalid GPS inputs preventing 500 crashes
    return redirect('admin_dashboard')

# 📸 UPDATE PROFILE
@login_required(login_url='login')
@require_POST
def update_profile(request):
    user = request.user
    user.department = request.POST.get('department')
    user.designation = request.POST.get('designation')
    if 'profile_picture' in request.FILES:
        user.profile_picture = request.FILES['profile_picture']
    user.save()
    return redirect('dashboard')

# 🏖️ LEAVE REQUESTS
@login_required(login_url='login')
@require_POST
def request_leave(request):
    start_str = request.POST.get('start_date')
    end_str = request.POST.get('end_date')
    reason = request.POST.get('reason')
    leave_type = request.POST.get('leave_type')
    
    if not start_str or not end_str or not reason or not leave_type:
        return redirect('dashboard') # Fast fail instead of throwing 500 error on empty parse
        
    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
    except ValueError:
        return redirect('dashboard') # 🛡️ Prevent 500 crashes from malicious date strings
        
    if start_date > end_date:
        return redirect('dashboard') # 🛡️ Prevent negative calendar durations

    if not LeaveRequest.objects.filter(user=request.user, start_date=start_date, end_date=end_date).exists():
        LeaveRequest.objects.create(
            user=request.user,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason
        )
        
    admin_emails = list(User.objects.filter(is_admin=True).values_list('email', flat=True))
    send_email_async('New Leave Request', f'{request.user.username} requested leave.', 'system@attendly.com', admin_emails)
    return redirect('dashboard')

@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def approve_leave(request, leave_id):
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    leave.status = 'Approved'
    leave.save()
    send_email_async('Leave Approved', f'Your {leave.leave_type} was approved.', 'admin@attendly.com', [leave.user.email])
    return redirect('admin_dashboard')

@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def reject_leave(request, leave_id):
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    leave.status = 'Rejected'
    leave.save()
    send_email_async('Leave Rejected', f'Your {leave.leave_type} was rejected.', 'admin@attendly.com', [leave.user.email])
    return redirect('admin_dashboard')

# 📊 EXPORT CSV
@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def export_attendance_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="attendance_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date', 'Employee', 'Department', 'Check In', 'Check Out', 'Late'])
    
    queryset = Attendance.objects.all().order_by('-date')
    start_date, end_date = request.GET.get('start_date'), request.GET.get('end_date')
    if start_date and end_date:
        try:
            queryset = queryset.filter(date__range=[start_date, end_date])
        except ValueError:
            return HttpResponse("Invalid date format. Expected YYYY-MM-DD.", status=400)
        
    for att in queryset.select_related('user').iterator(): # Use iterator to prevent Memory RAM explosion
        is_late = 'Yes' if att.check_in and att.user.shift_start and _extract_time(att.check_in) > att.user.shift_start else 'No'
        writer.writerow([att.date, att.user.get_full_name(), att.user.department, _extract_time(att.check_in), _extract_time(att.check_out), is_late])
    return response

# 🖨️ QR GENERATOR
@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def qr_generator(request):
    # 📍 Generate Secure Auto-Punch API URL
    signer = TimestampSigner()
    token = signer.sign('attendly_qr_punch')
    scanner_url = request.build_absolute_uri(f'/attendance/api/qr-attendance/?token={token}')
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(scanner_url)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return render(request, 'qr_generator.html', {'qr_image': img_str, 'scanner_url': scanner_url})

# 📄 EXTRA PAGES
@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def employee_list(request):
    employees = User.objects.filter(is_employee=True).order_by('first_name', 'last_name')
    return render(request, 'employees.html', {'employees': employees})

@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def employee_detail(request, emp_id):
    employee = get_object_or_404(User, id=emp_id)
    return render(request, 'employee_detail.html', {'employee': employee})

@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def edit_employee(request, emp_id):
    employee = get_object_or_404(User, id=emp_id)
    if request.method == 'POST':
        employee.department = request.POST.get('department')
        employee.designation = request.POST.get('designation')
        if request.POST.get('shift_start'):
            employee.shift_start = request.POST.get('shift_start')
        if request.POST.get('shift_end'):
            employee.shift_end = request.POST.get('shift_end')
        employee.save()
    return redirect('employee_detail', emp_id=employee.id)


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def attendance_page(request):
    # Fetch all attendance records from newest to oldest (Limited for performance)
    attendance_records = Attendance.objects.all().select_related('user').order_by('-date', '-check_in')[:500]
    
    # Evaluate late/early for each record
    for r in attendance_records:
        r.is_late = r.check_in and r.user.shift_start and _extract_time(r.check_in) > r.user.shift_start
        r.is_early = r.check_out and r.user.shift_end and _extract_time(r.check_out) < r.user.shift_end
        
    return render(request, 'attendance.html', {'attendance_records': attendance_records})


@login_required(login_url='login')
@user_passes_test(lambda u: u.is_admin, login_url='dashboard')
def reports_page(request):
    return render(request, 'reports.html')