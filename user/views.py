from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from core.models import (
    User,
    Transaction,
    Student,
    Guest,
    NewEnrollee,
    CAMPUS_CHOICES,
    QueueState,
    TransactionNF1,
    Department,
    Course,
    CutoffSchedule,
    TwoFactorToken
    )
import random
from django.core.mail import send_mail
from .forms import ChangePasswordForm, QueueModeForm, CashierForm
from django.http import JsonResponse
from django.utils.timezone import now, make_aware, get_current_timezone
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.db.models import Q
from django.utils.dateparse import parse_date
from django.utils import timezone
from datetime import datetime, timedelta, timezone as dt_timezone
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.utils.timezone import now, timedelta
from django.db.models.functions import TruncDate
from sklearn.linear_model import LinearRegression
import numpy as np
from django.utils.crypto import get_random_string
from django.urls import reverse
from django.db import transaction
from django.conf import settings
import logging
import os
from .email_sender import send_rolling_email

logger = logging.getLogger('custom_logger')


def login_user(request):
    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')
        request.session.flush()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.warning(f"Login failed — no user with email: {email}")
            messages.error(request, "Invalid email or password.")
            return redirect('login')

        if user.check_password(password):
            if user.verified:
                # Remove previous 2FA tokens for this user
                TwoFactorToken.objects.filter(user=user).delete()

                # 🔐 Generate new 6-digit code and token
                code = f"{random.randint(100000, 999999)}"
                token = TwoFactorToken.objects.create(user=user, code=code)

                logger.info(f"2FA code generated for {user.email} (ID: {user.id})")
                logger.debug(f"[2FA] Email: {user.email} | Code: {code} | Token: {token.token}")

                send_rolling_email(
                    subject='Your 2FA Code',
                    body=f'Your 2FA code is: {code}',
                    to_list=[user.email]
                )

                return redirect('verify_2fa_uuid', token=token.token)
            else:
                logger.warning(f"Unverified user tried to log in: {email}")
                messages.error(request, "Account is not verified.")
        else:
            logger.warning(f"Invalid credentials for email: {email}")
            messages.error(request, "Invalid email or password.")

        return redirect('login')

    return render(request, 'authenticate/login.html', {'site_key': settings.RECAPTCHA_SITE_KEY})


def verify_2fa_uuid(request, token):
    try:
        token_obj = TwoFactorToken.objects.get(token=token)
    except TwoFactorToken.DoesNotExist:
        messages.error(request, "Invalid or expired 2FA token.")
        return redirect('login')

    if token_obj.is_expired():
        token_obj.delete()
        messages.error(request, "This 2FA code has expired.")
        return redirect('login')

    if request.method == "POST":
        entered_code = request.POST.get('code')

        if entered_code == token_obj.code:
            user = token_obj.user
            user.isOnline = True
            user.save()

            request.session['user_id'] = user.id
            request.session['user_name'] = user.name
            request.session['window_num'] = user.windowNum
            request.session['is_admin'] = user.isAdmin

            logger.info(f"2FA success for {user.email} (ID: {user.id})")

            # Invalidate the token after successful use
            token_obj.delete()

            return redirect('admin_dashboard_summary' if user.isAdmin else 'cashier')

        else:
            logger.warning(f"Wrong 2FA code for user ID {token_obj.user.id}")
            messages.error(request, "Invalid 2FA code.")
            return redirect('verify_2fa_uuid', token=token)

    return render(request, 'authenticate/verify_2fa.html', {'token': token})



def cashier(request):
    user_id = request.session.get('user_id')

    if not user_id:
        messages.error(request, "Session expired. Please log in again.")
        return redirect('login')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('login')

    return render(request, 'cashier/dashboard.html', {'user': user})


def cashier_dashboard_data(request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JsonResponse({"error": "Session expired"}, status=403)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)

    return JsonResponse({
        "processing_mode": user.get_process_mode_display(),
        "email": user.email,
        "window_number": user.windowNum
    })


def logout_user(request):
    user_id = request.session.get('user_id')

    if user_id:
        try:
            user = User.objects.get(id=user_id)
            logger.debug(f"Logging out user: {user.email}, isOnline before: {user.isOnline}")

            with transaction.atomic():
                user.isOnline = False
                user.save(update_fields=['isOnline'])

            updated_status = User.objects.get(id=user.id).isOnline
            logger.debug(f"isOnline after save: {updated_status}")
            logger.info(f"User {user.email} (ID: {user.id}) logged out successfully.")

        except User.DoesNotExist:
            logger.warning(f"Logout attempt failed — user ID {user_id} not found.")

    request.session.flush()
    messages.success(request, "You have been logged out successfully.")
    logger.debug("Session data cleared. Redirecting to login page.")

    return redirect('login')


def department_list(request):

    depts = Department.objects.values('id', 'name')
    return JsonResponse(list(depts), safe=False)


def course_list(request):

    qs = Course.objects.all()
    dept_id = request.GET.get('department')
    if dept_id:
        qs = qs.filter(department_id=dept_id)
    courses = qs.values('id', 'name')
    return JsonResponse(list(courses), safe=False)



# Store tokens in a simple dict (in production use a DB model)
RESET_TOKENS = {}

def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            token = get_random_string(48)
            RESET_TOKENS[token] = user.id

            reset_link = request.build_absolute_uri(
                reverse('reset_password', args=[token])
            )

            logger.debug(f"[RESET] Password reset link generated for {email}: {reset_link}")
            logger.info(f"Password reset requested for user {user.email} (ID: {user.id})")

            # ✅ Use the rolling Gmail sender
            success = send_rolling_email(
                subject='Password Reset Link',
                body=f'Click the link to reset your password: {reset_link}',
                to_list=[user.email]
            )

            if success:
                logger.info(f"Password reset email sent to {user.email}")
                messages.success(request, "Reset link sent to your email.")
            else:
                messages.error(request, "Unable to send email. Please try again later.")

        except User.DoesNotExist:
            logger.warning(f"Password reset requested for non-existent email: {email}")
            messages.error(request, "No account associated with this email.")

    return render(request, 'authenticate/forgot_password.html')


def reset_password(request, token):
    user_id = RESET_TOKENS.get(token)
    if not user_id:
        logger.warning(f"Invalid or expired password reset token used: {token}")
        messages.error(request, "Invalid or expired reset link.")
        return redirect('login')

    if request.method == "POST":
        new_password = request.POST.get("password")
        try:
            user = User.objects.get(id=user_id)
            user.set_password(new_password)
            user.save()
            del RESET_TOKENS[token]

            logger.info(f"Password reset successful for user {user.email} (ID: {user.id})")
            messages.success(request, "Password has been reset. Please login.")
            return redirect('login')
        except User.DoesNotExist:
            logger.error(f"Password reset failed: user ID {user_id} not found.")
            messages.error(request, "User does not exist.")
            return redirect('login')

    return render(request, 'authenticate/reset_password.html', {"token": token})

"""

            ------------------------------          Function ng Cashiers            ------------------------------

"""

#Dashboard
def get_current_user(request):
    user_id = request.session.get('user_id')
    if user_id:
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
    return None


def cashier_dashboard_content(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthenticated access attempt to cashier profile.")
        return redirect("login")
    
    return render(request, 'cashier/partials/dashboard_content.html', {'user': user})


def cashier_profile_content(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthenticated access attempt to cashier profile.")
        return redirect("login")

    form = ChangePasswordForm()

    if request.method == "POST":
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            otp = f"{random.randint(100000, 999999)}"
            request.session["pending_password"] = form.cleaned_data["new_password"]
            request.session["password_otp"] = otp

            logger.debug(f"[OTP-GEN] Password change OTP for {user.email}: {otp}")
            logger.info(f"Password change OTP generated and sending to {user.email}")

            #Use your rolling email helper instead of send_mail
            subject = "OTP for Password Change"
            body = f"Your OTP code is: {otp}"
            to_list = [user.email]

            if send_rolling_email(subject, body, to_list):
                messages.success(request, "OTP sent to your email.")
            else:
                messages.error(request, "Failed to send OTP. Please try again later.")

            return redirect("verify_otp")
        else:
            logger.warning(f"Invalid password change form submitted by {user.email}")

    return render(request, "cashier/partials/profile_content.html", {"user": user, "form": form})


def print_cashier_transactions(request):
    user = get_current_user(request)
    if not user:
        return redirect("login")

    from_date = parse_date(request.GET.get("start_date", ""))
    to_date = parse_date(request.GET.get("end_date", ""))
    department_id = request.GET.get("department")
    course_id = request.GET.get("course")
    campus = request.GET.get("campus")

    transactions = TransactionNF1.objects.filter(reservedBy=user)

    if from_date:
        transactions = transactions.filter(created_at__date__gte=from_date)
    if to_date:
        transactions = transactions.filter(created_at__date__lte=to_date)
    if department_id:
        transactions = transactions.filter(course__department_id=department_id)
    if course_id:
        transactions = transactions.filter(course_id=course_id)
    if campus:
        transactions = transactions.filter(campus=campus)

    transactions = transactions.select_related("student", "guest", "new_enrollee", "course__department")

    department = None
    course = None
    try:
        if department_id:
            department = Department.objects.get(id=department_id)
        if course_id:
            course = Course.objects.get(id=course_id)
    except (Department.DoesNotExist, Course.DoesNotExist):
        pass

    results = []
    for txn in transactions:
        requester = txn.get_requester()
        role = type(requester).__name__ if requester else "Unknown"
        id_number = getattr(requester, 'studentId', getattr(requester, 'qrId', 'N/A'))
        name = getattr(requester, 'name', str(requester))
        results.append({
            "queue": txn.queueNumber,
            "id_number": id_number,
            "name": name,
            "role": role,
        })

    context = {
        "cashier": user,
        "transactions": results,
        "from_date": from_date,
        "to_date": to_date,
        "department": department,
        "course": course,
        "campus": campus,
    }

    template = get_template("cashier/transaction_print.html")
    html = template.render(context)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="filtered_transactions.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)
    if pisa_status.err:
        return HttpResponse("Error generating PDF", status=500)

    return response


def verify_otp(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthenticated user attempted to verify OTP.")
        return redirect("login")

    if request.method == "POST":
        entered_otp = request.POST.get("otp")
        expected_otp = request.session.get("password_otp")
        new_pw = request.session.get("pending_password")

        if entered_otp == expected_otp:
            user.set_password(new_pw)
            user.save()

            logger.info(f"OTP verified and password updated for user {user.email} (ID: {user.id})")
            logger.debug(f"[OTP-SUCCESS] Entered OTP matched for {user.email}")

            # 🧠 Send confirmation email using rolling Gmail SMTP
            subject = "Password Changed Successfully"
            body = (
                f"Hello {user.name},\n\n"
                "Your password has been successfully updated.\n\n"
                "If you did not request this change, please contact support immediately."
            )

            sent = send_rolling_email(subject, body, [user.email])

            if sent:
                logger.info(f"✅ Confirmation email sent to {user.email}")
            else:
                logger.error(f"⚠️ Failed to send confirmation email to {user.email}")

            # Clear OTP-related session data
            request.session.pop("password_otp", None)
            request.session.pop("pending_password", None)

            messages.success(request, "Password updated successfully.")
            return redirect("cashier_profile_content")
        else:
            logger.warning(f"[OTP-FAIL] Invalid OTP entered by user {user.email}")
            messages.error(request, "Invalid OTP.")

    return render(request, "cashier/partials/verify_otp.html", {})


def cashier_settings_content(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthenticated user attempted to access cashier settings.")
        return redirect("login")

    form = QueueModeForm(instance=user)

    if request.method == "POST":
        form = QueueModeForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            logger.info(f"Queue mode updated for user {user.email} (ID: {user.id})")
            messages.success(request, "Queue Processing Mode updated.")

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                logger.debug(f"Queue mode update submitted via AJAX by {user.email}")
                return JsonResponse({"success": True})

            logger.debug(f"Queue mode update submitted via full POST by {user.email}")
            return redirect("cashier_settings_content")
        else:
            logger.warning(f"Invalid queue mode form submission by user {user.email}")

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        html = render_to_string("cashier/partials/settings_content.html", {
            "form": form,
            "user": user
        }, request=request)
        logger.debug(f"Settings content rendered via AJAX for {user.email}")
        return JsonResponse({"html": html})

    logger.warning(f"Non-AJAX request blocked at cashier_settings_content by {user.email}")
    return HttpResponseBadRequest("This view is meant to be loaded via AJAX only.")



from django.utils.timezone import localdate, localtime


MIXED_PATTERN = [True, True, False, False]  # P, P, S, S


def get_next_transaction(user):
    today = localdate()
    qs = Transaction.objects.select_for_update().filter(
        status=Transaction.Status.ON_QUEUE,
        reservedBy__isnull=True,
        created_at__date=today
    )

    mode = user.process_mode
    if mode == user.ProcessMode.PRIORITY_ONLY:
        return qs.filter(priority=True).order_by('created_at').first()
    elif mode == user.ProcessMode.STANDARD_ONLY:
        return qs.filter(priority=False).order_by('created_at').first()
    elif mode == user.ProcessMode.MIXED:
        queue_state, _ = QueueState.objects.select_for_update().get_or_create(id=1)

        current_index = queue_state.position % len(MIXED_PATTERN)
        expected_priority = MIXED_PATTERN[current_index]

        filtered_qs = qs.filter(priority=expected_priority).order_by('created_at')
        next_txn = filtered_qs.first()

        if next_txn:
            queue_state.position = (queue_state.position + 1) % len(MIXED_PATTERN)
            queue_state.save(update_fields=['position'])
            return next_txn
        else:
            fallback_qs = qs.exclude(priority=expected_priority).order_by('created_at')
            return fallback_qs.first()

    return qs.order_by('created_at').first()




@require_POST
@transaction.atomic
def next_queue(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthorized access to next_queue endpoint.")
        return JsonResponse({"error": "Unauthorized"}, status=403)

    logger.debug(f"Resolving next_queue for user: {user.name}")
    today = localdate()

    # Step 1: Complete last NF1 transaction if exists
    current_txn_nf1 = TransactionNF1.objects.select_for_update().filter(
        reservedBy=user,
        status=TransactionNF1.Status.IN_PROCESS,
        created_at__date=today
    ).order_by('-created_at').first()

    if current_txn_nf1:
        logger.debug(f"Completing IN_PROCESS NF1 transaction: {current_txn_nf1.queueNumber}")
        TransactionNF1.objects.filter(pk=current_txn_nf1.pk).update(
            status=TransactionNF1.Status.COMPLETED
        )

        verified_txn = TransactionNF1.objects.get(pk=current_txn_nf1.pk)
        logger.debug(f"Verified NF1 {verified_txn.queueNumber} status after update: {verified_txn.status}")

        legacy_txn = Transaction.objects.filter(pk=current_txn_nf1.pk).first()
        if legacy_txn:
            legacy_txn.status = Transaction.Status.COMPLETED
            legacy_txn.save(update_fields=['status'])
            logger.debug(f"Legacy transaction {legacy_txn.queueNumber} updated to COMPLETED")
        else:
            logger.warning(f"No legacy transaction found for NF1 pk={current_txn_nf1.pk}")

    # Step 2: Ensure user has no active transaction
    has_active = Transaction.objects.filter(
        reservedBy=user,
        status=Transaction.Status.IN_PROCESS,
        created_at__date=today
    ).exists() or TransactionNF1.objects.filter(
        reservedBy=user,
        status=TransactionNF1.Status.IN_PROCESS,
        created_at__date=today
    ).exists()

    if has_active:
        logger.info(f"User {user.name} already has a transaction in process.")
        return JsonResponse({
            "error": "User already has a transaction in process."
        }, status=400)

    # Step 3: Reserve the next transaction
    next_txn = get_next_transaction(user)

    if next_txn:
        logger.debug(f"Reserving next transaction: {next_txn.queueNumber}")

        TransactionNF1.objects.filter(pk=next_txn.pk).update(
            status=TransactionNF1.Status.IN_PROCESS,
            reservedBy=user
        )

        legacy_txn = Transaction.objects.select_for_update().filter(pk=next_txn.pk).first()
        if legacy_txn:
            legacy_txn.status = Transaction.Status.IN_PROCESS
            legacy_txn.reservedBy = user
            legacy_txn.save(update_fields=['status', 'reservedBy'])
            logger.debug(f"Legacy transaction {legacy_txn.queueNumber} updated to IN_PROCESS")
        else:
            logger.warning(f"No legacy transaction found for next pk={next_txn.pk}")

        logger.info(f"Next queue reserved: {next_txn.queueNumber} by {user.name}")
        return JsonResponse({
            "success": True,
            "queue_number": next_txn.queueNumber
        })

    logger.info(f"User {user.name} completed transaction; no next queue available.")
    return JsonResponse({
        "success": True,
        "message": "Previous transaction completed. No queue available."
    })


def format_student_id(student_id: str) -> str:
    """Format student ID as xx-xxxx-xxxxxx."""
    if not student_id:
        return ""
    digits = "".join(filter(str.isdigit, student_id))
    # pad/truncate to 12 just in case
    digits = digits[:12].ljust(12, "0")
    return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"



def get_current_queue(request):
    user = get_current_user(request)
    if not user:
        return JsonResponse({}, status=403)

    today = localdate()

    txn = (
        Transaction.objects.filter(
            reservedBy=user,
            status=Transaction.Status.IN_PROCESS,
            created_at__date=today,
        )
        .order_by("-created_at")
        .first()
    )

    if txn:
        if txn.student:
            requester_name = txn.student.name
            role = "Student"
            student_Id_raw = txn.student.studentId
            student_Id = format_student_id(student_Id_raw)
        elif txn.new_enrollee:
            requester_name = f"New Enrollee - {txn.new_enrollee.pk}"
            role = "New Enrollee"
            student_Id_raw = None
            student_Id = None
        elif txn.guest:
            requester_name = f"Guest - {txn.guest.pk}"
            role = "Guest"
            student_Id_raw = None
            student_Id = None
        else:
            requester_name = "Unknown"
            role = "Unknown"
            student_Id_raw = None
            student_Id = None

        return JsonResponse({
            "queue_number": txn.queueNumber,
            "requester": requester_name,
            "role": role,
            "student_id": student_Id,         # formatted with dashes
            "student_id_raw": student_Id_raw, # original from DB
            "transaction_type": txn.transactionType,  # ✅ Added this line
            "transaction_for": txn.transaction_for,   # (optional) also useful if you want term info
        })

    return JsonResponse({})


@require_POST
def skip_queue(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthorized skip_queue attempt.")
        return JsonResponse({"error": "Unauthorized"}, status=403)

    # Step 1: Find current legacy transaction
    txn = Transaction.objects.filter(
        reservedBy=user,
        status=Transaction.Status.IN_PROCESS
    ).order_by('-created_at').first()

    if txn:
        queue_num = txn.queueNumber
        txn.status = Transaction.Status.CANCELLED
        txn.save()
        logger.info(f"Legacy transaction {queue_num} cancelled by user {user.name} (ID: {user.id})")

        # Step 2: Mirror cancellation to NF1
        updated_count = TransactionNF1.objects.filter(queueNumber=queue_num).update(
            status=TransactionNF1.Status.CANCELLED
        )

        if updated_count == 0:
            logger.warning(f"No NF1 transaction found for queueNumber {queue_num} during skip.")
        else:
            logger.debug(f"NF1 transaction {queue_num} cancelled successfully.")
    else:
        logger.info(f"No IN_PROCESS legacy transaction found for user {user.name} during skip.")

    return JsonResponse({"success": True})


def next_queues_list(request):
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    today = localdate()
    qs = Transaction.objects.filter(
        status=Transaction.Status.ON_QUEUE,
        reservedBy__isnull=True,
        created_at__date=today
    )

    mode = user.process_mode
    txns = []

    if mode == user.ProcessMode.PRIORITY_ONLY:
        txns = qs.filter(priority=True).order_by('created_at')[:10]

    elif mode == user.ProcessMode.STANDARD_ONLY:
        txns = qs.filter(priority=False).order_by('created_at')[:10]

    elif mode == user.ProcessMode.MIXED:
        from django.db import transaction
        with transaction.atomic():
            queue_state, _ = QueueState.objects.select_for_update().get_or_create(id=1)
            position = queue_state.position

            pattern = MIXED_PATTERN
            p_list = list(qs.filter(priority=True).order_by('created_at')[:20])
            s_list = list(qs.filter(priority=False).order_by('created_at')[:20])
            txns = []

            i = 0
            while len(txns) < 10 and (p_list or s_list):
                expected = pattern[(position + i) % len(pattern)]
                if expected and p_list:
                    txns.append(p_list.pop(0))
                elif not expected and s_list:
                    txns.append(s_list.pop(0))
                i += 1

    data = [
        {
            "queue_number": txn.queueNumber,
            "priority": txn.priority,
            "created_at": localtime(txn.created_at).strftime("%H:%M"),
        }
        for txn in txns
    ]
    return JsonResponse({"queues": data})


from django.db.models import F
# Hold Queue
@require_POST
def hold_queue(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthorized attempt to place queue on hold.")
        return JsonResponse({"error": "Unauthorized"}, status=403)

    txn = Transaction.objects.filter(
        reservedBy=user,
        status=Transaction.Status.IN_PROCESS
    ).first()

    if txn:
        queue_num = txn.queueNumber
        txn.status = Transaction.Status.ON_HOLD
        txn.onHoldCount += 1
        txn.save()

        logger.info(f"Transaction {queue_num} placed ON_HOLD by user {user.name} (ID: {user.id})")

        # Mirror update in NF1
        updated_count = TransactionNF1.objects.filter(queueNumber=queue_num).update(
            status=TransactionNF1.Status.ON_HOLD,
            onHoldCount=F('onHoldCount') + 1
        )

        if updated_count == 0:
            logger.warning(f"No NF1 transaction found to hold for queueNumber {queue_num}")
        else:
            logger.debug(f"NF1 transaction {queue_num} successfully updated to ON_HOLD.")
    else:
        logger.info(f"No active transaction found to hold for user {user.name}.")

    return JsonResponse({"success": True})

@require_GET
def list_on_hold_transactions(request):
    user = get_current_user(request)
    if not user:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    txns = Transaction.objects.filter(
        reservedBy=user,
        status=Transaction.Status.ON_HOLD
    ).order_by('-created_at')

    result = []
    for txn in txns:
        requester = txn.get_requester()

        if isinstance(requester, Student):
            name = requester.name
        elif isinstance(requester, NewEnrollee):
            name = "New Enrollee"
        elif isinstance(requester, Guest):
            name = "Guest"
        else:
            name = "Unknown"

        result.append({
            "id": txn.id,
            "queue_number": txn.queueNumber,
            "name": name,
            "type": txn.transactionType,
        })

    return JsonResponse({"holds": result})

import json

@require_POST
def update_hold_status(request):
    user = get_current_user(request)
    if not user:
        logger.warning("Unauthorized attempt to update hold status.")
        return JsonResponse({"error": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body)
        txn_id = data.get("id")
        new_status = data.get("status")
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Malformed JSON or missing keys in update_hold_status by {user.name}: {e}")
        return JsonResponse({"error": "Invalid request data"}, status=400)

    if new_status not in [Transaction.Status.COMPLETED, Transaction.Status.CANCELLED]:
        logger.warning(f"Invalid status '{new_status}' passed by user {user.name}")
        return JsonResponse({"error": "Invalid status"}, status=400)

    try:
        txn = Transaction.objects.get(
            id=txn_id,
            reservedBy=user,
            status=Transaction.Status.ON_HOLD
        )

        txn.status = new_status
        txn.save()
        logger.info(f"Transaction {txn.queueNumber} updated to {new_status} by user {user.name}")

        updated_count = TransactionNF1.objects.filter(queueNumber=txn.queueNumber).update(status=new_status)

        if updated_count == 0:
            logger.warning(f"No matching NF1 transaction for queueNumber {txn.queueNumber}")
        else:
            logger.debug(f"NF1 transaction {txn.queueNumber} updated to {new_status}")

        return JsonResponse({"success": True})

    except Transaction.DoesNotExist:
        logger.warning(f"Transaction with ID {txn_id} not found or not owned by user {user.name}")
        return JsonResponse({"error": "Not found"}, status=404)

    except Exception as e:
        logger.error(f"Unexpected error in update_hold_status for user {user.name}: {e}", exc_info=True)
        return JsonResponse({"error": "Internal Server Error"}, status=500)


"""

            ------------------------------       Admin Dashboard            ------------------------------

"""




def admin_dashboard(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})
    


    try:
        user = User.objects.get(id=user_id)
        if not user.isAdmin:
            return redirect('cashier')

        cashiers = User.objects.filter(isAdmin=False).order_by('windowNum')
        verified_count = cashiers.filter(verified=True).count()
        online_count = cashiers.filter(isOnline=True).count()
        non_verified = cashiers.filter(verified=False).count()
        verified = cashiers.filter(verified=True)

        html = render_to_string(
            'admin/partials/dashboard_summary.html',
            {
                'user': user,
                'cashiers': cashiers,
                'verified_count': verified_count,
                'online_count': online_count,
                'non_verified': non_verified,
                'verified': verified,
            },
            request=request 
        )
        return HttpResponse(html)

    except User.DoesNotExist:
        return redirect('login')
    

def admin_dashboard_summary(request):

    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})
    


    try:
        user = User.objects.get(id=user_id)
        if not user.isAdmin:
            return redirect('cashier')

        cashiers = User.objects.filter(isAdmin=False).order_by('windowNum')
        verified_count = cashiers.filter(verified=True).count()
        online_count = cashiers.filter(isOnline=True).count()
        non_verified = cashiers.filter(verified=False).count()
        verified = cashiers.filter(verified=True)

        html = render_to_string(
            'admin/partials/dashboard_summary.html',
            {
                'user': user,
                'cashiers': cashiers,
                'verified_count': verified_count,
                'online_count': online_count,
                'non_verified': non_verified,
                'verified': verified,
            },
            request=request 
        )
        return HttpResponse(html)

    except User.DoesNotExist:
        return redirect('login')

# Additional using the email helper



from django.views.decorators.csrf import csrf_exempt
import pytz

@csrf_exempt
def admin_queue_settings(request):
    user_id = request.session.get('user_id')

    if not user_id:
        logger.warning("Unauthenticated access to admin_queue_settings.")
        return redirect('login')

    if not request.session.get('is_admin', False):
        logger.warning(f"User {user_id} denied access to admin_queue_settings — not admin.")
        return render(request, 'unauthorized.html', {"message": "Admin access required."})

    message = None
    tz = get_current_timezone()

    if request.method == "POST":
        campus = request.POST.get('campus') or None
        cutoff_time_input = request.POST.get('cutoff_time')

        if cutoff_time_input:
            cutoff_time_naive = datetime.strptime(cutoff_time_input, "%Y-%m-%dT%H:%M")
            cutoff_time_ph = make_aware(cutoff_time_naive, tz)
        else:
            cutoff_time_ph = now().astimezone(tz)

        cutoff_time_utc = cutoff_time_ph.astimezone(pytz.UTC)
        now_utc = now().astimezone(pytz.UTC)
        is_cutoff_now = cutoff_time_utc <= now_utc

        logger.debug(f"[CUTOFF-SCHED] campus={campus}, cutoff_time={cutoff_time_utc}, now={now_utc}, immediate={is_cutoff_now}")

        cutoff = CutoffSchedule.objects.create(
            campus=campus,
            is_cutoff=is_cutoff_now,
            cutoff_time=cutoff_time_utc,
        )

        logger.info(f"Created CutoffSchedule ID={cutoff.id} for campus={campus} — immediate={is_cutoff_now}")

        updated_nf1 = 0
        updated_legacy = 0

        if is_cutoff_now:
            cutoff_date = cutoff_time_ph.date()
            txn_filters = {
                "status__in": ["on_queue", "on_hold"],
                "created_at__date": cutoff_date
            }
            txn_nf1_filters = txn_filters.copy()
            if campus:
                txn_nf1_filters["campus"] = campus

            updated_nf1 = TransactionNF1.objects.filter(**txn_nf1_filters).update(
                status=TransactionNF1.Status.CUT_OFF
            )

            legacy_txns = Transaction.objects.filter(**txn_filters)
            if campus:
                legacy_txns = legacy_txns.filter(
                    Q(student__campus=campus) |
                    Q(new_enrollee__campus=campus) |
                    Q(guest__campus=campus)
                )
            updated_legacy = legacy_txns.update(status=Transaction.Status.CUT_OFF)

            logger.info(f"Applied immediate cutoff -> NF1: {updated_nf1}, Legacy: {updated_legacy}")

            message = (
                f"✅ Cutoff applied for <strong>{campus or 'All Campuses'}</strong> at "
                f"<strong>{cutoff_time_ph.strftime('%Y-%m-%d %H:%M')}</strong>.<br>"
                f"NF1 affected: <strong>{updated_nf1}</strong>, "
                f"Legacy affected: <strong>{updated_legacy}</strong>."
            )
        else:
            logger.info(f"Scheduled cutoff saved for {campus or 'All Campuses'} at {cutoff_time_ph}")
            message = (
                f"⏳ Scheduled cutoff for <strong>{campus or 'All Campuses'}</strong> at "
                f"<strong>{cutoff_time_ph.strftime('%Y-%m-%d %H:%M')}</strong> has been saved."
            )

    manila_now = now().astimezone(tz)
    start_of_day = manila_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    start_utc = start_of_day.astimezone(pytz.UTC)
    end_utc = end_of_day.astimezone(pytz.UTC)

    today_cutoffs = CutoffSchedule.objects.filter(
        cutoff_time__gte=start_utc,
        cutoff_time__lt=end_utc
    ).order_by('-cutoff_time')

    current_user = User.objects.filter(id=user_id).first()
    return render(request, 'admin/partials/admin_queue_settings.html', {
        "user": current_user,
        "campuses": ["", "Main", "South", "San Jose"],
        "message": message,
        "cutoffs_today": today_cutoffs,
    })


def admin_logs(request):
    user_id = request.session.get('user_id')

    if not user_id:
        return redirect('login')

    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})

   
    
    return HttpResponse(render_to_string('admin/partials/logs.html', {}))


"""
-------------------------------------------------------------------------------------------------------------------------------- IIBAHIN
"""


def cashier_list_view(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})

    query = request.GET.get("search", "")

    verified_cashiers = User.objects.filter(verified=True, isAdmin=False)
    non_verified_cashiers = User.objects.filter(verified=False, isAdmin=False)

    if query:
        verified_cashiers = verified_cashiers.filter(
            Q(name__icontains=query) | Q(email__icontains=query)
        )
        non_verified_cashiers = non_verified_cashiers.filter(
            Q(name__icontains=query) | Q(email__icontains=query)
        )


    user = User.objects.filter(id=user_id).first()
    context = {
        "user": user,
        "verified_cashiers": verified_cashiers,
        "non_verified_cashiers": non_verified_cashiers,
        "search": query,
    }
    return render(request, "admin/partials/list.html", context)

def verify_cashier(request, cashier_id):
    if request.method == "POST":
        cashier = get_object_or_404(User, id=cashier_id, verified=False)
        cashier.verified = True
        cashier.save()
        
        # Email details
        subject = "Verification Successful"
        message = (
            f"Dear {cashier.name},\n\n"
            "Your cashier account has been verified and approved by the admin."
        )

        try:
            success = send_rolling_email(
                subject=subject,
                body=message,
                to_list=[cashier.email],
            )

            if success:
                messages.success(request, f"{cashier.name} has been verified and notified by email.")
            else:
                messages.warning(request, f"{cashier.name} has been verified, but email sending failed.")

        except Exception as e:
            print(f"[❌ EMAIL ERROR] Could not send verification email: {e}")
            messages.warning(request, f"{cashier.name} has been verified, but email sending encountered an error.")

    return redirect("cashier_list")



def reject_cashier(request, cashier_id):
    if request.method == "POST":
        cashier = get_object_or_404(User, id=cashier_id, verified=False)
        
        # Send rejection email before deletion
        send_mail(
            subject="Verification Rejected",
            message=f"Dear {cashier.name},\n\nWe regret to inform you that your cashier account has been rejected by the admin.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[cashier.email],
        )
        cashier.delete()
        messages.success(request, f"{cashier.name} has been rejected and deleted.")
    return redirect('cashier_list')

def cashier_transactions_view(request, cashier_id):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})
    

    from_date = parse_date(request.GET.get("start_date", ""))
    to_date = parse_date(request.GET.get("end_date", ""))
    department_id = request.GET.get("department")
    course_id = request.GET.get("course")
    campus = request.GET.get("campus")

    transactions = TransactionNF1.objects.filter(reservedBy_id=cashier_id)

    if from_date:
        transactions = transactions.filter(created_at__date__gte=from_date)
    if to_date:
        transactions = transactions.filter(created_at__date__lte=to_date)
    if department_id:
        transactions = transactions.filter(course__department_id=department_id)
    if course_id:
        transactions = transactions.filter(course_id=course_id)
    if campus:
        transactions = transactions.filter(campus=campus)

    # Optimize query
    transactions = transactions.select_related("student", "guest", "new_enrollee", "course__department")

    # Build results list manually with role and dynamic ID
    results = []
    for txn in transactions:
        requester = txn.get_requester()
        role = type(requester).__name__ if requester else "Unknown"
        results.append({
            "id_number": getattr(requester, 'studentId', getattr(requester, 'qrId', 'N/A')),
            "name": getattr(requester, 'name', str(requester)),
            "role": role,
            "queue": txn.queueNumber,
        })

    # Paginate the results
    paginator = Paginator(results, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)


    currect_user = User.objects.filter(id=user_id).first()
    context = {
        "user": currect_user,
        "cashier": get_object_or_404(User, pk=cashier_id),
        "transactions": page_obj,
        "departments": Department.objects.all(),
        "courses": Course.objects.all(),
        "campuses": [c[0] for c in CAMPUS_CHOICES],
    }
    return render(request, "admin/partials/transactions.html", context)


def get_courses_by_department(request):
    department_id = request.GET.get('department_id')
    courses = Course.objects.filter(department_id=department_id).values('id', 'name')
    return JsonResponse(list(courses), safe=False)


def cashier_update_view(request, cashier_id):
    cashier = get_object_or_404(User, pk=cashier_id)
    form = CashierForm(request.POST or None, instance=cashier)

    if form.is_valid():
        form.save()
        logger.info(f"Cashier (ID: {cashier.id}, Email: {cashier.email}) updated successfully.")
        return redirect('cashier_list')
    else:
        if request.method == "POST":
            logger.warning(f"Cashier update failed validation for ID: {cashier.id}")

    return render(request, 'admin/partials/edit_cashier.html', {'form': form, 'cashier': cashier})


@require_POST
def cashier_delete_view(request, cashier_id):
    cashier = get_object_or_404(User, pk=cashier_id)
    
    logger.info(f"Deleting cashier: ID={cashier.id}, Email={cashier.email}")
    cashier.delete()
    logger.info(f"Cashier ID={cashier.id} deleted successfully.")

    return redirect('cashier_list')


"""
-----------------------------------------------------------------------------------------------------------------------------

"""

# Search for Student
def student_list_view(request):

    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})
    query = request.GET.get("q", "")

    students_qs = Student.objects.filter(
        Q(name__icontains=query) | Q(studentId__icontains=query)
    ).order_by('name') if query else Student.objects.all().order_by('name')

    paginator = Paginator(students_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    priority_requests = Student.objects.filter(priority_request=True).order_by('name')
    approved_students = Student.objects.filter(priority=True).order_by('name')

    priority_count = priority_requests.count()


    user = User.objects.filter(id=user_id).first()
    return render(request, "admin/partials/students.html", {
        "user": user,
        "students": page_obj,
        "query": query,
        "page_obj": page_obj,
        "priority_requests": priority_requests,
        "approved_students": approved_students,
        "priority_count": priority_count,
    })


@require_POST
def update_priority_requests(request):
    approved_ids = request.POST.getlist('approved_ids')
    revoked_ids = request.POST.getlist('revoked_ids')

    if approved_ids:
        Student.objects.filter(id__in=approved_ids).update(priority=True, priority_request=False)

    if revoked_ids:
        Student.objects.filter(id__in=revoked_ids).update(priority=False)

    messages.success(request, "Priority changes have been saved.")
    return redirect('student_list')


def student_transactions_ajax(request, student_id):
    student = get_object_or_404(Student, id=student_id)

    transactions = Transaction.objects.filter(
        student=student
    ).order_by("-created_at")

    txn_data = [
        {
            "queueNumber": txn.queueNumber,
            "type": txn.transactionType,
            "status": txn.get_status_display(),  # Better: human-readable
            "priority": txn.priority,
            "created": txn.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for txn in transactions
    ]

    return JsonResponse({
        "transactions": txn_data,
        "student_name": student.name
    })



def kpi_data(request):
    # Convert to Manila local time
    today = localtime(now()).date()
    start_date = today - timedelta(days=6)

    # Transactions on queue today
    on_queue_today = TransactionNF1.objects.filter(
        created_at__date=today,
        status=TransactionNF1.Status.ON_QUEUE
    ).count()

    # Status counts for today
    status_counts = (
        TransactionNF1.objects
        .filter(created_at__date=today)
        .values('status')
        .annotate(count=Count('id'))
    )

    tracked_statuses = [
        TransactionNF1.Status.ON_HOLD,
        TransactionNF1.Status.COMPLETED,
        TransactionNF1.Status.CUT_OFF,
    ]

    # 7-day status breakdown
    raw_counts = (
        TransactionNF1.objects
        .filter(
            created_at__date__range=(start_date, today),
            status__in=tracked_statuses
        )
        .annotate(day=TruncDate('created_at'))
        .values('day', 'status')
        .annotate(count=Count('id'))
    )

    # Daily data structuring
    day_range = [start_date + timedelta(days=i) for i in range(7)]
    trend_data = {status: [] for status in tracked_statuses}

    for status in tracked_statuses:
        daily_counts = {entry['day']: entry['count'] for entry in raw_counts if entry['status'] == status}
        for day in day_range:
            trend_data[status].append({
                'date': day.isoformat(),
                'count': daily_counts.get(day, 0)
            })

    # Linear regression forecast
    forecast = {}
    for status in tracked_statuses:
        y = np.array([point['count'] for point in trend_data[status]])
        X = np.array(range(7)).reshape(-1, 1)
        model = LinearRegression().fit(X, y)
        pred = int(model.predict(np.array([[7]])).round()[0])
        forecast[status] = pred

    # Queue breakdown
    queued_today = TransactionNF1.objects.filter(
        created_at__date=today,
        status=TransactionNF1.Status.ON_QUEUE
    )
    student_count = queued_today.filter(student_id__isnull=False).count()
    new_enrollee_count = queued_today.filter(new_enrollee_id__isnull=False).count()
    guest_count = queued_today.filter(guest_id__isnull=False).count()

    return JsonResponse({
        'on_queue_today': on_queue_today,
        'status_counts': list(status_counts),
        'transaction_trends': trend_data,
        'forecast': forecast,
        'queue_breakdown': {
            'students': student_count,
            'new_enrollees': new_enrollee_count,
            'guests': guest_count
        }
    })


def kpi_summary(request):
    manila_now = localtime(now())  # Converts UTC to Asia/Manila automatically using TIME_ZONE
    today = manila_now.date()
    yesterday = today - timedelta(days=1)

    verified_cashiers = User.objects.filter(verified=True)

    results = []
    for cashier in verified_cashiers:
        today_count = TransactionNF1.objects.filter(
            reservedBy=cashier,
            status=TransactionNF1.Status.COMPLETED,
            created_at__date=today
        ).count()

        yesterday_count = TransactionNF1.objects.filter(
            reservedBy=cashier,
            status=TransactionNF1.Status.COMPLETED,
            created_at__date=yesterday
        ).count()

        delta = today_count - yesterday_count
        trend = "up" if delta > 0 else ("down" if delta < 0 else "equal")

        results.append({
            "cashier_name": cashier.name,
            "today": today_count,
            "yesterday": yesterday_count,
            "delta": abs(delta),
            "trend": trend
        })

    return JsonResponse({"data": results})


'''
---------------------------------------------------------------
'''

from collections import defaultdict

def admin_statistics(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    context = {
        "user": user,
        "departments": Department.objects.all(),
        "courses": Course.objects.all(),
    }
    return render(request, "admin/partials/statistics.html", context)


# Modify This
def get_date_range(time_filter):
    today = localdate()  # Asia/Manila local date

    if time_filter == "last_7_days":
        return [today - timedelta(days=i) for i in reversed(range(7))]

    elif time_filter == "this_month":
        start = today.replace(day=1)
        return [start + timedelta(days=i) for i in range((today - start).days + 1)]

    elif time_filter == "monthly":
        year_start = today.replace(month=1, day=1)
        return [year_start.replace(month=m) for m in range(1, today.month + 1)]

    elif time_filter == "today":
        return [today]

    elif time_filter == "weekly":
        start_of_week = today - timedelta(days=today.weekday())  # Monday as start
        return [start_of_week + timedelta(days=i) for i in range((today - start_of_week).days + 1)]

    else:
        return []



def statistics_data(request):

    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})
    
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)

    transactions = TransactionNF1.objects.filter(
        status=TransactionNF1.Status.COMPLETED,
        created_at__date__in=date_range
    )

    # Apply filters
    if campus:
        transactions = transactions.filter(campus__iexact=campus)
    if course:
        transactions = transactions.filter(course__id=course)
    if department:
        transactions = transactions.filter(course__department__id=department)
    if year:
        transactions = transactions.filter(student__year_level=year)
    if txn_for:
        transactions = transactions.filter(transaction_for=txn_for)

    # Grouping data
    results = {str(date): {} for date in date_range}
    for date in date_range:
        day_txns = transactions.filter(created_at__date=date)
        for campus_name in day_txns.values_list("campus", flat=True).distinct():
            count = day_txns.filter(campus=campus_name).count()
            results[str(date)][campus_name] = count

    all_campuses = sorted({camp for day in results.values() for camp in day})
    datasets = []

    for campus_name in all_campuses:
        data = [results[str(d)].get(campus_name, 0) for d in date_range]
        datasets.append({
            "label": campus_name,
            "data": data
        })

    return JsonResponse({
        "labels": [str(d) for d in date_range],
        "datasets": datasets
    })


def transaction_type_chart_data(request):
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)
    if not date_range:
        return JsonResponse({"labels": [], "datasets": []})

    start_date = date_range[0]

    queryset = TransactionNF1.objects.filter(
        status__iexact="completed",
        created_at__date__gte=start_date
    )

    # Apply filters
    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    # === Manual Count by transactionType ===
    counts = defaultdict(int)
    for txn in queryset:
        txn_type = txn.transactionType.strip().title() if txn.transactionType else "Unknown"
        counts[txn_type] += 1

    # Sort descending by count
    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    labels = [k for k, v in sorted_items]
    data = [v for k, v in sorted_items]

    return JsonResponse({
        "labels": labels,
        "datasets": [{
            "label": "Completed Transactions",
            "data": data,
            "backgroundColor": "rgba(75, 192, 192, 0.7)"
        }]
    })


def status_donut_chart_data(request):
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)
    if not date_range:
        return JsonResponse({"labels": [], "datasets": []})

    start_date = date_range[0]

    queryset = TransactionNF1.objects.filter(created_at__date__gte=start_date)

    # Apply filters
    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    # Count each status
    counts = defaultdict(int)
    for txn in queryset:
        status = txn.status.lower()
        counts[status] += 1

    if not counts:
        return JsonResponse({"labels": [], "data": []})

    # Format labels like "Completed: 35 (52%)"
    total = sum(counts.values())
    labels = []
    data = []
    for k, v in counts.items():
        label = f"{k.replace('_', ' ').title()}: {v} ({(v/total)*100:.2f}%)"
        labels.append(label)
        data.append(v)

    return JsonResponse({
        "labels": labels,
        "datasets": [{
            "data": data,
            "backgroundColor": generate_status_colors(len(data))
        }]
    })


def generate_status_colors(n):
    base = ['#36A2EB', '#FF6384', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40']
    return [base[i % len(base)] for i in range(n)]


def status_by_department_chart_data(request):
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)
    if not date_range:
        return JsonResponse({"labels": [], "datasets": []})

    start_date = date_range[0]

    queryset = TransactionNF1.objects.filter(
        created_at__date__gte=start_date,
        status__in=["completed", "cancelled", "cut_off"]
    )

    # Apply filters
    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    # Group counts by department and status
    data = defaultdict(lambda: {"Completed": 0, "Cancelled": 0, "Cut Off": 0})

    for txn in queryset.select_related("course__department"):
        dept = txn.course.department.name if txn.course and txn.course.department else "Unknown"
        status = txn.status.replace("_", " ").title()
        data[dept][status] += 1

    # Convert to Chart.js format
    labels = sorted(data.keys())
    status_keys = ["Completed", "Cancelled", "Cut Off"]
    datasets = []

    color_map = {
        "Completed": "#4dc9f6",
        "Cancelled": "#f67019",
        "Cut Off": "#f53794"
    }

    for status in status_keys:
        datasets.append({
            "label": status,
            "data": [data[dept].get(status, 0) for dept in labels],
            "backgroundColor": color_map[status]
        })

    return JsonResponse({
        "labels": labels,
        "datasets": datasets
    })


def heatmap_chart_data(request):
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)
    if not date_range:
        return JsonResponse({"series": [], "categories": []})

    queryset = TransactionNF1.objects.filter(created_at__date__in=date_range)

    # Apply filters
    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    # X-axis: Dates | Y-axis: Transaction Types
    date_labels = [str(d) for d in date_range]
    type_set = set()
    counts = defaultdict(int)

    for txn in queryset:
        tx_type = txn.transactionType.strip().title() if txn.transactionType else "Unknown"
        date_key = txn.created_at.date()
        type_set.add(tx_type)
        counts[(tx_type, date_key)] += 1

    # Build ApexCharts series
    type_list = sorted(type_set)
    series = []

    for tx_type in type_list:
        data = []
        for date in date_range:
            data.append({
                "x": str(date),
                "y": counts.get((tx_type, date), 0)
            })
        series.append({
            "name": tx_type,
            "data": data
        })

    return JsonResponse({
        "series": series,
        "categories": date_labels
    })


def hourly_heatmap_chart_data(request):
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)
    if not date_range:
        return JsonResponse({"series": [], "categories": []})

    queryset = TransactionNF1.objects.filter(
        status=TransactionNF1.Status.COMPLETED,
        created_at__date__in=date_range
    )

    # Apply filters
    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    # Grouping by hour (Y) and date (X)
    counts = defaultdict(int)
    dates = [str(d) for d in date_range]
    hours = [f"{h:02}:00" for h in range(24)]  # 00:00 to 23:00

    for txn in queryset:
        local_dt = txn.created_at.astimezone()  # Ensure local time
        hour_label = f"{local_dt.hour:02}:00"
        date_label = str(local_dt.date())
        counts[(hour_label, date_label)] += 1

    # Build ApexCharts-compatible data structure
    series = []
    for hour in hours:
        data = []
        for date in dates:
            data.append({
                "x": date,
                "y": counts.get((hour, date), 0)
            })
        series.append({
            "name": hour,
            "data": data
        })

    return JsonResponse({
        "series": series,
        "categories": dates
    })

from datetime import date, timedelta

# modify this also
def forecast_chart_data(request):
    today = localdate()  # Asia/Manila local date
    current_time = now()  # timezone-aware datetime

    time_filter = request.GET.get("time", "last_7_days")
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")

    date_range = get_date_range(time_filter)
    if not date_range:
        return JsonResponse({"labels": [], "series": []})

    # Step 1: Filter base queryset
    queryset = TransactionNF1.objects.filter(
        status=TransactionNF1.Status.COMPLETED,
        created_at__date__in=date_range
    )

    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)
    if year:
        queryset = queryset.filter(student__year_level=year)

    # Step 2: Aggregate daily counts
    daily_counts = defaultdict(int)
    for txn in queryset:
        txn_date = txn.created_at.astimezone().date()  # Use local date
        daily_counts[txn_date] += 1

    # Step 3: Calculate average hourly pattern for forecasting
    hour_totals = defaultdict(int)
    day_set = set()

    for txn in queryset:
        local_dt = txn.created_at.astimezone()
        hour = local_dt.hour
        txn_date = local_dt.date()
        hour_totals[hour] += 1
        day_set.add(txn_date)

    total_days = len(day_set) or 1
    avg_by_hour = {h: hour_totals[h] / total_days for h in range(24)}

    # Step 4: Prepare labels and values (replace today's date with "Today")
    labels = []
    values = []

    for d in date_range:
        label = "Today" if d == today else str(d)
        labels.append(label)
        values.append(daily_counts.get(d, 0))

    # Step 5: Today’s actual + projected value
    today_actual_qs = TransactionNF1.objects.filter(
        status=TransactionNF1.Status.COMPLETED,
        created_at__date=today
    )
    if campus:
        today_actual_qs = today_actual_qs.filter(campus__iexact=campus)
    if course:
        today_actual_qs = today_actual_qs.filter(course__id=course)
    if department:
        today_actual_qs = today_actual_qs.filter(course__department__id=department)

    today_actual = today_actual_qs.count()
    current_hour = current_time.hour

    projected_remaining = sum(avg_by_hour.get(h, 0) for h in range(current_hour + 1, 18))
    projected_today = today_actual + projected_remaining

    # Update or append today's forecasted value
    if "Today" in labels:
        idx = labels.index("Today")
        values[idx] = round(projected_today)
    else:
        labels.append("Today")
        values.append(round(projected_today))

    # Step 6: Forecast for tomorrow
    # Step 6: Forecast for next period (day/week/month)
    next_label = None
    next_forecast = 0

    if time_filter in ["last_7_days", "today", "weekly"]:
        # Next day (Tomorrow)
        next_date = today + timedelta(days=1)
        next_label = "Tomorrow"
        next_forecast = sum(avg_by_hour.get(h, 0) for h in range(6, 18))

    elif time_filter == "this_month":
        # Next month (if exists)
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year if today.month < 12 else today.year + 1
        next_label = f"{date(next_year, next_month, 1):%B}"
        # Rough estimate: average daily * typical number of working days (22)
        avg_daily = sum(values) / len(values) if values else 0
        next_forecast = round(avg_daily * 22)

    elif time_filter == "monthly":
        # Next year forecast
        next_label = str(today.year + 1)
        avg_monthly = sum(values) / len(values) if values else 0
        next_forecast = round(avg_monthly * 12)

    else:
        # Default: Tomorrow
        next_label = "Tomorrow"
        next_forecast = sum(avg_by_hour.get(h, 0) for h in range(6, 18))

    labels.append(next_label)
    values.append(round(next_forecast))


    return JsonResponse({
        "labels": labels,
        "series": values,
        "actual_today": today_actual
    })


from django.db.models import F, ExpressionWrapper, DurationField, Avg
from django.db.models.functions import Now

def average_processing_time_view(request):
    # Filters (same as others)
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)
    if not date_range:
        return JsonResponse({"average_minutes": 0})

    queryset = TransactionNF1.objects.filter(
        status=TransactionNF1.Status.COMPLETED,
        created_at__date__in=date_range
    )

    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if course:
        queryset = queryset.filter(course__id=course)
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    queryset = queryset.annotate(
        processing_time=ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField())
    )

    avg_duration = queryset.aggregate(avg=Avg('processing_time'))['avg']

    if avg_duration:
        avg_minutes = round(avg_duration.total_seconds() / 60, 2)
    else:
        avg_minutes = 0

    return JsonResponse({"average_minutes": avg_minutes})


TRANSACTION_FOR_CHOICES = [
    ('enrollment', 'Enrollment'),
    ('sem_1', 'Sem 1'),
    ('sem_2', 'Sem 2'),
    ('summer', 'Summer'),
    ('off_term', 'Off Term'),
]

def sem_transaction_type_grouped_chart(request):
    valid_sems = ["sem_1", "sem_2", "summer"]
    valid_tx_types = ["P1", "P2", "P3"]

    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    time_filter = request.GET.get("time", "last_7_days")

    date_range = get_date_range(time_filter)
    queryset = TransactionNF1.objects.filter(
        status=TransactionNF1.Status.COMPLETED,
        transaction_for__in=valid_sems,
        transactionType__in=valid_tx_types,
        created_at__date__in=date_range
    )

    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if course:
        queryset = queryset.filter(course__id=course)
    if year:
        queryset = queryset.filter(student__year_level=year)

    grouped = defaultdict(lambda: defaultdict(int))  # sem -> tx_type -> count

    for txn in queryset:
        sem = dict(TRANSACTION_FOR_CHOICES).get(txn.transaction_for, txn.transaction_for)
        tx_type = txn.transactionType.upper()
        grouped[sem][tx_type] += 1

    # dynamically get valid sems display names from TRANSACTION_FOR_CHOICES
    sems = [label for key, label in TRANSACTION_FOR_CHOICES if key in valid_sems]
    tx_types = valid_tx_types

    series = []
    for sem in sems:
        data = [grouped[sem].get(tx_type, 0) for tx_type in tx_types]
        series.append({"name": sem, "data": data})

    return JsonResponse({
        "categories": tx_types,
        "series": series
    })


from collections import Counter


def priority_breakdown_view(request):
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    # Handle date range safely using local timezone
    today = localdate()
    if time_filter == "last_7_days":
        start_date = today - timedelta(days=6)
    elif time_filter == "this_month":
        start_date = today.replace(day=1)
    elif time_filter == "today":
        start_date = today
    else:
        return JsonResponse({ "error": "Invalid time filter" }, status=400)

    # Query: only completed transactions
    queryset = TransactionNF1.objects.filter(
        status__iexact="completed",
        created_at__date__gte=start_date
    )

    # Apply filters
    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
    if department:
        queryset = queryset.filter(course__department__id=department)
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    # Count priority vs non-priority
    priority_list = [bool(txn.priority) for txn in queryset]
    counts = Counter(priority_list)

    values = [counts.get(False, 0), counts.get(True, 0)]
    total = sum(values)
    percentages = [(v / total * 100 if total else 0) for v in values]

    return JsonResponse({
        "time_filter": time_filter.replace("_", " ").title(),
        "department": department,
        "course": course,
        "campus": campus,
        "non_priority": {
            "count": values[0],
            "percentage": round(percentages[0], 2)
        },
        "priority": {
            "count": values[1],
            "percentage": round(percentages[1], 2)
        }
    })


from xhtml2pdf import pisa
from io import BytesIO


def generate_transaction_pdf(request):
    campus = request.GET.get("campus")
    department = request.GET.get("department")
    course = request.GET.get("course")
    year = request.GET.get("year")
    txn_for = request.GET.get("transaction_for")
    time_filter = request.GET.get("time", "last_7_days")

    # Use timezone-aware local date
    today = localdate()
    if time_filter == "last_7_days":
        start_date = today - timedelta(days=6)
    elif time_filter == "this_month":
        start_date = today.replace(day=1)
    elif time_filter == "today":
        start_date = today
    else:
        start_date = today - timedelta(days=6)

    queryset = TransactionNF1.objects.filter(created_at__date__gte=start_date)

    department_obj = None
    course_obj = None

    # Apply filters
    if campus:
        queryset = queryset.filter(campus__iexact=campus)
    if course:
        queryset = queryset.filter(course__id=course)
        try:
            course_obj = Course.objects.get(id=course)
        except Course.DoesNotExist:
            pass
    if department:
        queryset = queryset.filter(course__department__id=department)
        try:
            department_obj = Department.objects.get(id=department)
        except Department.DoesNotExist:
            pass
    if year:
        queryset = queryset.filter(student__year_level=year)
    if txn_for:
        queryset = queryset.filter(transaction_for=txn_for)

    queryset = queryset.order_by('created_at')

    html_string = render_to_string("admin/partials/transaction_report.html", {
        "transactions": queryset,
        "time_filter": time_filter.replace("_", " ").title(),
        "generated_at": now(),  # timezone-aware timestamp
        "campus": campus,
        "department": department_obj,
        "course": course_obj,
    })

    result = BytesIO()
    pdf_status = pisa.CreatePDF(src=html_string, dest=result)

    if pdf_status.err:
        return HttpResponse("Error rendering PDF", status=500)

    return HttpResponse(result.getvalue(), content_type='application/pdf')

from django.template.loader import get_template


def cashier_transactions_pdf_view(request, cashier_id):
    from_date = parse_date(request.GET.get("start_date", ""))
    to_date = parse_date(request.GET.get("end_date", ""))
    department_id = request.GET.get("department")
    course_id = request.GET.get("course")
    campus = request.GET.get("campus")

    department_name = Department.objects.filter(pk=department_id).first().name if department_id else "All"
    course_name = Course.objects.filter(pk=course_id).first().name if course_id else "All"
    campus_name = campus if campus else "All"

    transactions = TransactionNF1.objects.filter(reservedBy_id=cashier_id)
    if from_date:
        transactions = transactions.filter(created_at__date__gte=from_date)
    if to_date:
        transactions = transactions.filter(created_at__date__lte=to_date)
    if department_id:
        transactions = transactions.filter(course__department_id=department_id)
    if course_id:
        transactions = transactions.filter(course_id=course_id)
    if campus:
        transactions = transactions.filter(campus=campus)

    transactions = transactions.select_related("student", "guest", "new_enrollee", "course__department")

    results = []
    for txn in transactions:
        requester = txn.get_requester()
        role = type(requester).__name__ if requester else "Unknown"
        results.append({
            "id_number": getattr(requester, 'studentId', getattr(requester, 'qrId', 'N/A')),
            "name": getattr(requester, 'name', str(requester)),
            "role": role,
            "queue": txn.queueNumber,
        })

    context = {
        "cashier": get_object_or_404(User, pk=cashier_id),
        "transactions": results,
        "filters": {
            "start_date": from_date.strftime("%Y-%m-%d") if from_date else "All",
            "end_date": to_date.strftime("%Y-%m-%d") if to_date else "All",
            "department": department_name,
            "course": course_name,
            "campus": campus_name,
        }
    }

    template = get_template("admin/partials/transactions_pdf.html")
    html = template.render(context)
    response = HttpResponse(content_type="application/pdf")
    pdf_status = pisa.CreatePDF(html, dest=response)

    if pdf_status.err:
        return HttpResponse("Failed to generate PDF", status=500)

    return response




"""
LoGGINGS -------------------------------------------


"""

LOG_FILE_PATH = os.path.join(settings.BASE_DIR, 'logs/django_events.log')



def log_viewer(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login')
    
    if not request.session.get('is_admin', False):
        return render(request, 'unauthorized.html', {"message": "Admin access required."})

    query = request.GET.get("q", "").lower()
    level_filter = request.GET.get("level", "").upper()

    log_entries = []

    if os.path.exists(LOG_FILE_PATH):
        try:
            with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="replace") as log_file:
                for line in reversed(log_file.readlines()):
                    # Skip GET request logs
                    if "GET /" in line:
                        continue
                    if query and query not in line.lower():
                        continue
                    if level_filter and f"{level_filter}" not in line:
                        continue
                    log_entries.append(line.strip())
        except Exception as e:
            log_entries.append(f"Error reading log file: {e}")

    user = User.objects.filter(id=user_id).first()
    return render(request, "admin/partials/log_viewer.html", {
        "user": user,
        "logs": log_entries[:500],  # limit to latest 500
        "query": query,
        "level": level_filter
    })

