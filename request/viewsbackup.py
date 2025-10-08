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
from django.core.mail import EmailMessage
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


def generate_otp(length=6):
    return ''.join(random.choices('0123456789', k=length))

class OTPForm(forms.Form):
    otp = forms.CharField(label="Enter the OTP sent to your email", max_length=6)

def register_student(request, token=None):
    session_key = f'student_token_{token}' if token else None

    if request.method == 'POST':
        # OTP verification
        if 'verify_otp' in request.POST and token:
            otp_form = OTPForm(request.POST)
            session_data = request.session.get(session_key)

            if otp_form.is_valid() and session_data:
                user_otp = otp_form.cleaned_data['otp']
                if user_otp == session_data['otp']:
                    form_data = session_data['form_data']
                    form = StudentRegistrationForm(form_data)

                    if form.is_valid():
                        with transaction.atomic():
                            student = form.save(commit=False)
                            student.qrId = generate_qr_id()
                            student.save()

                        # Trigger Celery task asynchronously
                        generate_qr_and_send_email.delay(student.id)

                        # Clean up session
                        del request.session[session_key]

                        messages.success(request, "Student registered successfully! QR code sent via email.")
                        return redirect(reverse('student_success', args=[student.id]))
                    else:
                        messages.error(request, "Internal form data is invalid.")
                else:
                    messages.error(request, "Incorrect OTP. Please try again.")

            return render(request, 'request/register_student.html', {'otp_form': otp_form})

        # Registration form submission (initial POST)
        else:
            form = StudentRegistrationForm(request.POST)
            if form.is_valid():
                otp = generate_otp()
                token = str(uuid.uuid4())
                session_key = f'student_token_{token}'
                request.session[session_key] = {
                    'form_data': request.POST,
                    'otp': otp,
                }

                email = EmailMessage(
                    subject='Your Verification Code',
                    body=f'Hello {form.cleaned_data["name"]},\n\nYour verification code is: {otp}',
                    from_email='noreply@phinmaed.com',
                    to=[form.cleaned_data['email']],
                )
                email.send(fail_silently=False)

                messages.info(request, "A verification code was sent to your email.")
                return redirect(f'/student_register={token}/')
            else:
                return render(request, 'request/register_student.html', {
                    'form': form,
                    'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY,
                })

    # GET request (either first-time or after redirect)
    if token:
        otp_form = OTPForm()
        return render(request, 'request/register_student.html', {'otp_form': otp_form})

    form = StudentRegistrationForm()
    return render(request, 'request/register_student.html', {
        'form': form,
        'recaptcha_site_key': settings.RECAPTCHA_SITE_KEY,
    })


def student_success(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    return render(request, 'request/student_success.html', {'student': student})



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
    """
    Generate a queue number like P-0001 or S-0001,
    restarting count each day based on created_at date.
    """
    prefix = 'P' if priority else 'S'

    # Use timezone-aware current time if not provided
    if created_at is None:
        created_at = now()

    txn_date = created_at.date()

    count = Transaction.objects.filter(
        created_at__date=txn_date,
        priority=priority
    ).count() + 1

    return f"{prefix}-{count:04d}"


def request_queue(request):
    if request.method == 'POST':
        form = QueueRequestForm(request.POST)
        if form.is_valid():
            qr_id = form.cleaned_data['qrId']
            transaction_type = form.cleaned_data['transactionType']
            today = now().date()

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

            # Only restrict Students
            if isinstance(requester, Student):
                existing_txn = TransactionNF1.objects.filter(
                    student_id=requester.id,
                    created_at__date=today
                ).order_by('-created_at').first()

                if existing_txn and existing_txn.status not in [
                    TransactionNF1.Status.COMPLETED,
                    TransactionNF1.Status.CANCELLED,
                    TransactionNF1.Status.CUT_OFF
                ]:
                    messages.error(request, "Student already has an active transaction today.")
                    return redirect('request_queue')

            # Ensure priority field is defined
            if requester.priority is None:
                requester.priority = False
                requester.save(update_fields=["priority"])

            priority = requester.priority
            queue_number = generate_queue_number(priority)

            timestamp = now()  # Already timezone-aware

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

            messages.success(request, f"Transaction created: {txn_nf1.queueNumber}")
            return redirect('request_queue')
    else:
        form = QueueRequestForm()

    return render(request, 'request/request_queue.html', {'form': form})


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
        for txn in qs.filter(priority=True)[:10]
    ]

    standard_queues = [
        {
            "queue_number": txn.queueNumber,
            "created_at": localtime(txn.created_at).strftime("%H:%M"),
        }
        for txn in qs.filter(priority=False)[:10]
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

                # Add logo to QR
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

                # Save QR image to buffer
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)

                # Send via email
                email_message = EmailMessage(
                    subject='Your Student QR Code (Recovery)',
                    body=f'Hi {student.name},\n\nHere is a copy of your student QR code.',
                    from_email='noreply@phinmaed.com',
                    to=[student.email],
                )
                email_message.attach('qr.png', buffer.read(), 'image/png')
                email_message.send(fail_silently=False)

                messages.success(request, "Your QR code has been sent to your email.")
                return redirect('register_student')
            except Student.DoesNotExist:
                form.add_error('email', 'No student found with this email.')
    else:
        form = QRRecoveryForm()

    return render(request, 'request/recover_qr.html', {'form': form})
