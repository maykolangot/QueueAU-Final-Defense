from django.urls import path

from django.conf import settings
from django.conf.urls.static import static
from .views import (
    register_student,
    student_success,
    register_new_enrollee,
    register_guest,
    request_queue,
    load_courses,
    register_view,
    index,
    live_queue_status,
    live_queue_page, public_next_queues,
    recover_qr,
    new_enrollee_quick_queue,
    guest_quick_queue
    )

urlpatterns = [
    path('ajax/load-courses/', load_courses, name='ajax_load_courses'),
    path('student_register=<str:token>/', register_student, name='register_student'),
    path('student_register/', register_student, name='register_student'),
    path('student/success/<int:student_id>/', student_success, name='student_success'),
    path('student/recover_qr/', recover_qr, name='recover_qr'),

    # Remove on the thingies
    path('new-enrollee/', register_new_enrollee, name='register_new_enrollee'),
    path('guest/', register_guest, name='register_guest'),
    path('queue-request/', request_queue, name='request_queue'),
    path('queue-request/new-enrollee/', new_enrollee_quick_queue, name='new_enrollee_quick_queue'),
    path('queue-request/guest/', guest_quick_queue, name='guest'),

    path('cashier_register/',register_view, name='register'),
    path('', index, name='index'),
    path("live-queue/", live_queue_status, name="live-queue-status"),
    path("live-queue-page/", live_queue_page, name="live-queue-page"),
    path("public-next-queues/", public_next_queues, name="public-next-queues"),



] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
