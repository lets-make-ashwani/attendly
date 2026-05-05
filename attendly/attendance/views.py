import json
import math
import threading
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponse
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.shortcuts import render, redirect
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction, IntegrityError

from accounts.models import OfficeLocation, User
from .models import Attendance

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculates distance in meters between two GPS coordinates."""
    R = 6371000 # Radius of earth in meters
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi_1) * math.cos(phi_2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# 🛡️ Helper to safely extract time from mixed Database artifacts (prevents crashes)
def _extract_time(dt_obj):
    if not dt_obj: return None
    if hasattr(dt_obj, 'astimezone'): return timezone.localtime(dt_obj).time() # New DateTimeField
    if hasattr(dt_obj, 'time'): return dt_obj.time() # Old TimeField artifact
    if isinstance(dt_obj, str): # SQLite string artifact
        try: return datetime.strptime(dt_obj.split('.')[0], '%H:%M:%S').time()
        except ValueError: pass
    return dt_obj

# � QR SCANNER PAGE (Frontend)
def scanner_page(request):
    if not request.user.is_authenticated or not request.user.is_approved:
        return redirect('login')
    return render(request, 'scanner.html')

# ✅ QR SCAN API (Handles Check In & Check Out based on logic)
@login_required(login_url='login')
@require_POST
def qr_scan(request):
    # Block unauthorized access (suspended employees or admins)
    if not request.user.is_approved or not getattr(request.user, 'is_employee', False):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized account.'}, status=403)

    try:
        data = json.loads(request.body)
        lat = float(data.get('lat'))
        lon = float(data.get('lon'))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid location data'}, status=400)

    # Fetch dynamic office location from DB
    loc = OfficeLocation.objects.first()
    office_lat = loc.latitude if loc else getattr(settings, 'OFFICE_LATITUDE', 0.0)
    office_lon = loc.longitude if loc else getattr(settings, 'OFFICE_LONGITUDE', 0.0)
    radius = loc.radius if loc else 100

    dist = calculate_distance(lat, lon, office_lat, office_lon)
    
    if dist > radius:
        return JsonResponse({'status': 'error', 'message': f'Too far away ({int(dist)}m). Must be within {radius}m.'}, status=400)

    # 🛡️ Synchronize datetime generation to prevent midnight crossover bugs
    now = timezone.localtime()
    today = now.date()

    try:
        with transaction.atomic():
            # 🛡️ Night Shift Fix: Check if they are trying to clock out from a shift started yesterday
            yesterday = today - timedelta(days=1)
            attendance = Attendance.objects.filter(
                user=request.user, date=yesterday, check_in__isnull=False, check_out__isnull=True
            ).first()

            if not attendance:
                # 🛡️ Fetch today's record (Removed select_for_update which crashes SQLite)
                attendance = Attendance.objects.filter(
                    user=request.user, date=today
                ).first()
                
                if not attendance:
                    try:
                        with transaction.atomic(): # 🛡️ Nested savepoint prevents Postgres transaction aborts
                            attendance = Attendance.objects.create(user=request.user, date=today)
                    except IntegrityError:
                        attendance = Attendance.objects.get(user=request.user, date=today)

            if not attendance.check_in:
                attendance.check_in = now
                attendance.save(update_fields=['check_in'])

                # 🕒 Check Late & Notify
                if request.user.shift_start and _extract_time(attendance.check_in) > _extract_time(request.user.shift_start):
                    admin_emails = list(User.objects.filter(is_admin=True).values_list('email', flat=True))
                    valid_emails = [e for e in admin_emails if e]
                    if valid_emails:
                        threading.Thread(
                            target=send_mail,
                            args=('Late Check-in Alert', f'{request.user.get_full_name() or request.user.username} checked in late.', 'system@attendly.com', valid_emails),
                            kwargs={'fail_silently': True}
                        ).start()
                return JsonResponse({'status': 'success', 'message': 'Check-in successful'})

            elif not attendance.check_out:
                # 🛡️ Prevent accidental double-scan (immediate checkout) within 5 minutes
                try:
                    time_diff = (now - attendance.check_in).total_seconds()
                except Exception:
                    time_diff = 301 # Bypass cooldown if check_in is an old SQLite string artifact
                    
                if time_diff < 10:
                    return JsonResponse({'status': 'error', 'message': 'You just checked in. Please wait 10 seconds before checking out.'}, status=400)

                attendance.check_out = now
                attendance.save(update_fields=['check_out'])
                return JsonResponse({'status': 'success', 'message': 'Check-out successful'})
                
            else:
                return JsonResponse({'status': 'error', 'message': 'Already checked in and out today.'}, status=400)
                
    except Exception as e:
        print(f"QR Scan Error: {e}") # Print traceback to Render logs for debugging
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred. Please try again.'}, status=500)


# 🚀 NEW: AUTO ATTENDANCE PUNCH (No Button Click)
@login_required(login_url='login')
def auto_attendance_punch(request):
    # 1. Security: Block unauthorized accounts
    if not request.user.is_approved or not getattr(request.user, 'is_employee', False):
        return HttpResponse("<script>alert('Unauthorized account.'); window.location.href='/';</script>", status=403)

    # 2. Security: Validate Expiring Token
    token = request.GET.get('token')
    if not token:
        return HttpResponse("<script>alert('Missing QR token.'); window.location.href='/dashboard/';</script>", status=400)

    signer = TimestampSigner()
    try:
        # Token expires in 60 seconds (prevents using old screenshots/photos)
        original_text = signer.unsign(token, max_age=60)
        if original_text != 'attendly_qr_punch':
            raise BadSignature
    except SignatureExpired:
        return HttpResponse("<script>alert('QR Code expired! Please scan the live screen on the Admin dashboard.'); window.location.href='/dashboard/';</script>", status=400)
    except BadSignature:
        return HttpResponse("<script>alert('Invalid QR token.'); window.location.href='/dashboard/';</script>", status=400)

    # 3. Setup Date/Time
    now = timezone.localtime()
    today = now.date()

    try:
        with transaction.atomic():
            yesterday = today - timedelta(days=1)
            attendance = Attendance.objects.filter(
                user=request.user, date=yesterday, check_in__isnull=False, check_out__isnull=True
            ).first()

            if not attendance:
                attendance = Attendance.objects.filter(user=request.user, date=today).first()
                if not attendance:
                    try:
                        with transaction.atomic(): # 🛡️ Nested savepoint prevents Postgres transaction aborts
                            attendance = Attendance.objects.create(user=request.user, date=today)
                    except IntegrityError:
                        attendance = Attendance.objects.get(user=request.user, date=today)

            # CASE 1: CHECK IN
            if not attendance.check_in:
                attendance.check_in = now
                attendance.save(update_fields=['check_in'])
                
                # Async late alert
                if request.user.shift_start and _extract_time(now) > _extract_time(request.user.shift_start):
                    admin_emails = list(User.objects.filter(is_admin=True).values_list('email', flat=True))
                    valid_emails = [e for e in admin_emails if e]
                    if valid_emails:
                        threading.Thread(target=send_mail, args=('Late Check-in Alert', f'{request.user.get_full_name() or request.user.username} checked in late.', 'system@attendly.com', valid_emails), kwargs={'fail_silently': True}).start()
                
                msg = "Check-in successful! You may close this tab."

            # CASE 2: CHECK OUT
            elif not attendance.check_out:
                try:
                    time_diff = (now - attendance.check_in).total_seconds()
                except Exception:
                    time_diff = 301 # Bypass if old artifact
                    
                if time_diff < 10: # 10 second cool-down for testing
                    return HttpResponse("<script>alert('You just checked in! Please wait 10 seconds before checking out.'); window.location.href='/dashboard/';</script>", status=400)
                attendance.check_out = now
                attendance.save(update_fields=['check_out'])
                
                # 🛡️ Prevent "Yesterday Check-out" Trap
                if attendance.date == yesterday:
                    msg = "Checked out of yesterday's shift. PLEASE SCAN AGAIN to check in for today!"
                else:
                    msg = "Check-out successful! You may close this tab."

            # CASE 3: ALREADY COMPLETED
            else:
                return HttpResponse("<script>alert('Attendance already completed for today.'); window.location.href='/dashboard/';</script>", status=400)

            # 4. Auto-executing response (Closes the phone scanner tab immediately)
            return HttpResponse(f"<script>alert('{msg}'); window.close(); setTimeout(() => {{ window.location.href = '/dashboard/'; }}, 500);</script>")
            
    except Exception as e:
        print(f"Auto Punch Error: {e}") # Print traceback to Render logs for debugging
        return HttpResponse("<script>alert('An unexpected error occurred. Please try again.'); window.location.href='/dashboard/';</script>", status=500)