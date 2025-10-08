from celery import shared_task
from django.core.mail import EmailMessage
from core.models import Student
from PIL import Image
import qrcode
import io


@shared_task
def generate_qr_and_send_email(student_id):
    student = Student.objects.select_related('course', 'course__department').get(pk=student_id)

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(student.qrId)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

    logo_path = '/static/aulogo.png'
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

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    email = EmailMessage(
        subject='Your Student QR Code',
        body=f'Hi {student.name},\n\nThank you for registering. Attached is your QR code.',
        from_email='noreply@phinmaed.com',
        to=[student.email],
    )
    email.attach('qr.png', buffer.read(), 'image/png')
    email.send(fail_silently=False)

