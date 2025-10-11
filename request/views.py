from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now
from core.models import Student, Transaction, Guest, NewEnrollee, TransactionNF1, Course
from .forms import StudentRegistrationForm, NewEnrolleeForm, GuestForm, QueueRequestForm, RegisterUser
from .utils import generate_qr_id
from django.shortcuts import get_object_or_404
from django.urls import reverse
import qrcode
import io
from django.core.mail import EmailMessage, get_connection
from django.http import JsonResponse
from .printing import print_queue_slip
from django.utils.timezone import localtime, now, make_aware, localdate
from django.conf import settings
from PIL import Image
from django.db import transaction
import random
from django import forms
from .tasks import generate_qr_and_send_email
import uuid
import os
from io import BytesIO
import base64
from uuid import UUID
from django.db.models import Q
import threading


def generate_otp(length=6):
    return ''.join(random.choices('0123456789', k=length))

class OTPForm(forms.Form):
    otp = forms.CharField(label="Enter the OTP sent to your email", max_length=6)


# Rather than sending the QR to the Student, generate the QR when successfully registered
def register_student(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                student = form.save(commit=False)
                student.qrId = generate_qr_id()
                student.save()

            messages.success(
                request,
                "Student registered successfully! QR code is shown below."
            )
            return redirect(reverse('student_success', args=[student.id]))
        else:
            return render(request, 'request/register_student.html', {
                'form': form,
                'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY,
            })

    # GET request → show registration form
    form = StudentRegistrationForm()
    return render(request, 'request/register_student.html', {
        'form': form,
        'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY,
    })


def student_success(request, student_id):
    student = get_object_or_404(Student, id=student_id)

    # Generate QR code dynamically with AU logo
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(student.qrId)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    logo_path = os.path.join(settings.BASE_DIR, 'static', 'aulogo.png')
    try:
        logo = Image.open(logo_path)
        base_width = img.size[0] // 4
        w_percent = base_width / float(logo.size[0])
        h_size = int((float(logo.size[1]) * w_percent))
        logo = logo.resize((base_width, h_size), Image.Resampling.LANCZOS)
        pos = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
        img.paste(logo, pos, mask=logo if logo.mode == 'RGBA' else None)
    except FileNotFoundError:
        pass

    # Convert QR image to base64 for rendering
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return render(request, 'request/student_success.html', {
        'student': student,
        'qr_code': qr_base64,
    })



'''

-------------------------------             Guest and New Enrollees Temporary           ------------------------------------------

'''


# 📧 This is where all notifications go
NOTIFY_EMAIL = 'michael.magdosa.au@phinmaed.com'

def register_new_enrollee(request):
    if request.method == 'POST':
        form = NewEnrolleeForm(request.POST)
        if form.is_valid():
            enrollee = form.save(commit=False)
            enrollee.qrId = generate_qr_id()
            enrollee.save()

            # QR code now contains only the QR ID
            qr = qrcode.make(enrollee.qrId)
            buffer = io.BytesIO()
            qr.save(buffer, format='PNG')
            buffer.seek(0)

            email = EmailMessage(
                subject='New Enrollee Registered',
                body=f'QR ID: {enrollee.qrId}',
                from_email='noreply@phinmaed.com',
                to=[NOTIFY_EMAIL],
            )
            email.attach('enrollee_qr.png', buffer.read(), 'image/png')
            email.send(fail_silently=False)

            messages.success(request, "New enrollee registered. QR code sent via email.")
            return redirect('register_new_enrollee')
    else:
        form = NewEnrolleeForm()

    return render(request, 'request/new_enrollee_form.html', {'form': form})


def register_guest(request):
    if request.method == 'POST':
        form = GuestForm(request.POST)
        if form.is_valid():
            guest = form.save(commit=False)
            guest.qrId = generate_qr_id()
            guest.save()

            qr = qrcode.make(guest.qrId)
            buffer = io.BytesIO()
            qr.save(buffer, format='PNG')
            buffer.seek(0)

            email = EmailMessage(
                subject='New Guest Registered',
                body=f'QR ID: {guest.qrId}',
                from_email='noreply@phinmaed.com',
                to=[NOTIFY_EMAIL],
            )
            email.attach('guest_qr.png', buffer.read(), 'image/png')
            email.send(fail_silently=False)

            messages.success(request, "Guest registered. QR code sent via email.")
            return redirect('register_guest')
    else:
        form = GuestForm()

    return render(request, 'request/guest_form.html', {'form': form})



'''
-------------------------------------       Request Queue Number        -------------------------------------
'''

def generate_queue_number(priority: bool, created_at=None):
    prefix = 'P' if priority else 'S'

    # Use Django's timezone-aware "now"
    if created_at is None:
        created_at = timezone.localtime(timezone.now())

    # Normalize to the start of the local day using Django's timezone
    start_of_day = created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    count_legacy = Transaction.objects.filter(
        created_at__gte=start_of_day,
        created_at__lt=end_of_day,
        priority=priority
    ).count()

    count_nf1 = TransactionNF1.objects.filter(
        created_at__gte=start_of_day,
        created_at__lt=end_of_day,
        priority=priority
    ).count()

    next_num = max(count_legacy, count_nf1) + 1
    return f"{prefix}-{next_num:04d}"



def request_queue(request):
    if request.method == 'POST':
        form = QueueRequestForm(request.POST)
        if form.is_valid():
            qr_id = form.cleaned_data['qrId']
            transaction_type = form.cleaned_data['transactionType']
            today = now().date()

            # --- Identify requester ---
            requester = None
            requester_type = None
            for model_class in [Student, Guest, NewEnrollee]:
                try:
                    requester = model_class.objects.get(qrId=qr_id)
                    requester_type = model_class.__name__
                    break
                except model_class.DoesNotExist:
                    continue

            if not requester:
                messages.error(request, "QR ID not found.")
                return redirect('request_queue')

            # --- Campus cutoff check ---
            campus = getattr(requester, "campus", None)
            if is_campus_cutoff(campus):
                messages.error(
                    request,
                    f"Queue requests for {campus or 'this campus'} are closed due to cutoff."
                )
                return redirect('request_queue')

            # --- Student restriction (only one active txn) ---
            if isinstance(requester, Student):
                existing_txn = TransactionNF1.objects.filter(
                    student_id=requester.id,
                    status__in=[
                        TransactionNF1.Status.ON_QUEUE,
                        TransactionNF1.Status.ON_HOLD,
                        TransactionNF1.Status.IN_PROCESS
                    ]
                ).exists()

                if existing_txn:
                    messages.error(request, "You already have an active transaction.")
                    return redirect('request_queue')


            # --- Ensure priority is defined ---
            if requester.priority is None:
                requester.priority = False
                requester.save(update_fields=["priority"])

            priority = requester.priority
            queue_number = generate_queue_number(priority)
            timestamp = now()

            # --- Create NF1 transaction ---
            txn_nf1 = TransactionNF1.create_from_requester(
                requester=requester,
                transaction_type=transaction_type,
                queue_number=queue_number
            )
            txn_nf1.status = TransactionNF1.Status.ON_QUEUE
            txn_nf1.priority = priority
            txn_nf1.created_at = timestamp
            txn_nf1.save(update_fields=["status", "priority", "created_at"])

            # --- Create legacy transaction ---
            Transaction.objects.create(
                queueNumber=txn_nf1.queueNumber,
                transactionType=txn_nf1.transactionType,
                status=txn_nf1.status,
                priority=txn_nf1.priority,
                onHoldCount=txn_nf1.onHoldCount,
                created_at=txn_nf1.created_at,
                reservedBy=txn_nf1.reservedBy,
                student=txn_nf1.student,
                new_enrollee=txn_nf1.new_enrollee,
                guest=txn_nf1.guest,
            )

            # --- Print queue slip asynchronously (avoid broken pipe) ---
            transaction.on_commit(lambda: threading.Thread(
                target=print_queue_slip,
                args=(txn_nf1.queueNumber, txn_nf1.transactionType),
                daemon=True
            ).start())

            messages.success(request, f"Transaction created: {txn_nf1.queueNumber}")
            return redirect('request_queue')
    else:
        form = QueueRequestForm()

    return render(request, 'request/request_queue.html', {'form': form})




from core.models import CutoffSchedule
from django.utils.timezone import now, get_current_timezone
from datetime import timedelta
import pytz


def is_campus_cutoff(campus: str) -> bool:
    """
    Check if the given campus has an active cutoff for today.
    Returns True if requests should be blocked.
    """

    tz = get_current_timezone()  # Usually Asia/Manila
    current_time = now().astimezone(tz)

    # Today's boundaries (local Manila time)
    start_of_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    # Convert to UTC for DB query (since cutoff_time is stored in UTC)
    start_utc = start_of_day.astimezone(pytz.UTC)
    end_utc = end_of_day.astimezone(pytz.UTC)

    # Find the most recent cutoff today for this campus (or global cutoff if no campus specified)
    cutoff = (
        CutoffSchedule.objects.filter(
            Q(campus=campus) | Q(campus__isnull=True) | Q(campus="")
        )
        .filter(cutoff_time__gte=start_utc, cutoff_time__lt=end_utc)
        .order_by("-cutoff_time")
        .first()
    )

    if not cutoff:
        return False  # No cutoff scheduled for today

    # Convert cutoff_time from UTC to local timezone before comparison
    cutoff_local = cutoff.cutoff_time.astimezone(tz)

    # Active if: already marked as cutoff OR local time is past cutoff
    return cutoff.is_cutoff or current_time >= cutoff_local



def new_enrollee_quick_queue(request):
    """
    Quickly creates a queue entry for a New Enrollee with fixed UUID,
    transaction purpose 'Enrollment', and transaction type 'Downpayment'.
    """
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect('request_queue')

    uuid_value = UUID("31d84936-01cf-437d-931b-52ee5cd64309")
    transaction_for = "Enrollment"
    transaction_type = "Downpayment"
    today = now().date()

    try:
        requester = NewEnrollee.objects.get(qrId=uuid_value)
    except NewEnrollee.DoesNotExist:
        messages.error(request, "New Enrollee QR ID not found.")
        return redirect('request_queue')

    if requester.priority is None:
        requester.priority = False
        requester.save(update_fields=["priority"])

    priority = requester.priority
    queue_number = generate_queue_number(priority)
    timestamp = now()

    txn_nf1 = TransactionNF1.create_from_requester(
        requester=requester,
        transaction_type=transaction_type,
        queue_number=queue_number
    )
    txn_nf1.status = TransactionNF1.Status.ON_QUEUE
    txn_nf1.priority = priority
    txn_nf1.created_at = timestamp
    txn_nf1.save(update_fields=["status", "priority", "created_at"])

    Transaction.objects.create(
        queueNumber=txn_nf1.queueNumber,
        transactionType=txn_nf1.transactionType,
        status=txn_nf1.status,
        priority=txn_nf1.priority,
        onHoldCount=txn_nf1.onHoldCount,
        created_at=txn_nf1.created_at,
        reservedBy=txn_nf1.reservedBy,
        student=txn_nf1.student,
        new_enrollee=txn_nf1.new_enrollee,
        guest=txn_nf1.guest,
    )

    print_queue_slip(txn_nf1.queueNumber, txn_nf1.transactionType)
    messages.success(request, f"Quick queue created for {transaction_for}: {txn_nf1.queueNumber}")
    return redirect('request_queue')



def guest_quick_queue(request):
    """
    Quickly creates a queue entry for a Guest with fixed UUID,
    transaction purpose 'Guest Transaction', and transaction type 'Inquiry'.
    """
    if request.method != "POST":
        messages.error(request, "Invalid request method.")
        return redirect('request_queue')

    uuid_value = UUID("e28ad113-cbad-45af-be85-582e422bd4b4")
    transaction_for = "Tenants/Guest"
    transaction_type = "Guest Payment"  # or whatever is appropriate
    today = now().date()

    try:
        requester = Guest.objects.get(qrId=uuid_value)
    except Guest.DoesNotExist:
        messages.error(request, "Guest QR ID not found.")
        return redirect('request_queue')

    if requester.priority is None:
        requester.priority = False
        requester.save(update_fields=["priority"])

    priority = requester.priority
    queue_number = generate_queue_number(priority)
    timestamp = now()

    txn_nf1 = TransactionNF1.create_from_requester(
        requester=requester,
        transaction_type=transaction_type,
        queue_number=queue_number
    )
    txn_nf1.status = TransactionNF1.Status.ON_QUEUE
    txn_nf1.priority = priority
    txn_nf1.created_at = timestamp
    txn_nf1.save(update_fields=["status", "priority", "created_at"])

    Transaction.objects.create(
        queueNumber=txn_nf1.queueNumber,
        transactionType=txn_nf1.transactionType,
        status=txn_nf1.status,
        priority=txn_nf1.priority,
        onHoldCount=txn_nf1.onHoldCount,
        created_at=txn_nf1.created_at,
        reservedBy=txn_nf1.reservedBy,
        student=txn_nf1.student,
        new_enrollee=txn_nf1.new_enrollee,
        guest=txn_nf1.guest,
    )

    print_queue_slip(txn_nf1.queueNumber, txn_nf1.transactionType)
    messages.success(request, f"Quick queue created for {transaction_for}: {txn_nf1.queueNumber}")
    return redirect('request_queue')


def load_courses(request):
    department_id = request.GET.get('department_id')
    courses = Course.objects.filter(department_id=department_id).order_by('name')
    return JsonResponse(list(courses.values('id', 'name')), safe=False)


def register_view(request):
    form = RegisterUser(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('login')

    return render(request, 'request/register.html', {
        'form': form,
        'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY,
    })


def index(request):
    # you can pass context data here if needed
    return render(request, 'index.html', {
        'welcome_text': 'Welcome to QueueAU!',
    })

from django.http import JsonResponse
from django.utils import timezone
import pytz

from core.models import User, TransactionNF1

def live_queue_status(request):
    # Set timezone to Asia/Manila
    manila_tz = pytz.timezone("Asia/Manila")
    today = timezone.now().astimezone(manila_tz).date()

    # Get online users
    online_users = User.objects.filter(isOnline=True)

    # Get in-process transactions reserved by online users, created/updated today
    transactions = TransactionNF1.objects.filter(
        reservedBy__in=online_users,
        status=TransactionNF1.Status.IN_PROCESS,
        updated_at__date=today
    ).select_related('reservedBy')

    # Format response
    result = [
        {
            "window": t.reservedBy.windowNum,
            "queue_number": t.queueNumber,
            "status": t.status
        }
        for t in transactions
    ]

    return JsonResponse(result, safe=False)


def live_queue_page(request):
    return render(request, 'live_queue.html')

# Re
def public_next_queues(request):
    today = localdate()
    qs = Transaction.objects.filter(
        status=Transaction.Status.ON_QUEUE,
        reservedBy__isnull=True,
        created_at__date=today
    ).order_by('created_at')

    priority_queues = [
        {
            "queue_number": txn.queueNumber,
            "created_at": localtime(txn.created_at).strftime("%H:%M"),
        }
        for txn in qs.filter(priority=True)[:5]
    ]

    standard_queues = [
        {
            "queue_number": txn.queueNumber,
            "created_at": localtime(txn.created_at).strftime("%H:%M"),
        }
        for txn in qs.filter(priority=False)[:5]
    ]

    on_hold_queues = [
        {
            "queue_number": txn.queueNumber,
            "created_at": localtime(txn.created_at).strftime("%H:%M"),
        }
        for txn in Transaction.objects.filter(
            status=Transaction.Status.ON_HOLD,
            created_at__date=today
        ).order_by('created_at')
    ]

    return JsonResponse({
        "priority": priority_queues,
        "standard": standard_queues,
        "on_hold": on_hold_queues
    })


# Lost QR Code

from django.core.exceptions import ObjectDoesNotExist

class QRRecoveryForm(forms.Form):
    email = forms.EmailField(label="Enter your registered email")

from .email_sender import send_rolling_email



def recover_qr(request):
    if request.method == 'POST':
        form = QRRecoveryForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                student = Student.objects.get(email=email)

                # Generate QR code
                qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
                qr.add_data(student.qrId)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

                # Add logo if available
                logo_path = 'static/aulogo.png'
                try:
                    logo = Image.open(logo_path)
                    base_width = img.size[0] // 4
                    w_percent = base_width / float(logo.size[0])
                    h_size = int((float(logo.size[1]) * w_percent))
                    logo = logo.resize((base_width, h_size), Image.Resampling.LANCZOS)
                    pos = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
                    img.paste(logo, pos, mask=logo if logo.mode == 'RGBA' else None)
                except FileNotFoundError:
                    messages.warning(request, "QR sent without logo: logo file not found.")

                # Save QR to bytes
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                qr_bytes = buffer.read()

                # Email details
                subject = 'Your Student QR Code (Recovery)'
                body = f'Hi {student.name},\n\nHere is a copy of your student QR code.'

                # ✅ Send using the rolling Gmail SMTP
                sent = send_rolling_email(
                    subject=subject,
                    body=body,
                    to_list=[student.email],
                    attachments=[('qr.png', qr_bytes, 'image/png')]
                )

                if sent:
                    messages.success(request, "Your QR code has been sent to your email.")
                else:
                    messages.error(request, "Failed to send QR code. Please try again later.")

                return redirect('register_student')

            except Student.DoesNotExist:
                form.add_error('email', 'No student found with this email.')
    else:
        form = QRRecoveryForm()

    return render(request, 'request/recover_qr.html', {'form': form})
