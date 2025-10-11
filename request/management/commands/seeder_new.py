import random
from datetime import datetime, timedelta, time

from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware

from core.models import (
    Student, Guest, NewEnrollee,
    TransactionNF1, Transaction, User
)

from request.views import generate_queue_number


TRANSACTION_TYPE = [
    # Payment Phases & Common Transactions
    ('Downpayment', 'Downpayment'),
    ('Miscellaneous', 'Miscellaneous'),
    ('Payment', 'Payment'),
    ('P1', 'P1'),
    ('P2', 'P2'),
    ('P3', 'P3'),
    ('INC Completion', 'INC Completion'),

    # One-time & Miscellaneous Fees
    ('Registration Fee', 'Registration Fee'),
    ('Laboratory Fee', 'Laboratory Fee'),
    ('Library Fee', 'Library Fee'),
    ('ID Replacement Fee', 'ID Replacement Fee'),
    ('Graduation Fee', 'Graduation Fee'),
    ('Certificate Issuance Fee', 'Certificate Issuance Fee'),
    ('Transcript of Records Request', 'Transcript of Records Request'),
    ('Diploma Request', 'Diploma Request'),
    ('Late Enrollment Penalty', 'Late Enrollment Penalty'),
    ('Miscellaneous Fee', 'Miscellaneous Fee'),

    # Special Workshops & Programs
    ('Workshop Fee', 'Workshop Fee'),
    ('Seminar Fee', 'Seminar Fee'),
    ('Continuing Education', 'Continuing Education'),

    # Academic Services
    ('Subject Overload Request', 'Subject Overload Request'),
    ('Subject Withdrawal', 'Subject Withdrawal'),
    ('Cross Enrollment', 'Cross Enrollment'),
    ('Shifting Request', 'Shifting Request'),
    ('Leave of Absence', 'Leave of Absence'),
    ('Reinstatement Request', 'Reinstatement Request'),
    ('Change of Schedule', 'Change of Schedule'),

    # Document Requests
    ('Good Moral Certificate', 'Good Moral Certificate'),
    ('Honorable Dismissal', 'Honorable Dismissal'),
    ('Course Description Request', 'Course Description Request'),
    ('Enrollment Verification', 'Enrollment Verification'),
    ('Student Copy of Grades', 'Student Copy of Grades'),
    ('English Proficiency Certificate', 'English Proficiency Certificate'),

    # ID & System Access
    ('Student Portal Issue', 'Student Portal Issue'),
    ('ID Application', 'ID Application'),
    ('RFID Access Request', 'RFID Access Request'),

    # Financial Aid & Clearance
    ('Scholarship Application', 'Scholarship Application'),
    ('Payment Discrepancy', 'Payment Discrepancy'),
    ('Clearance Processing', 'Clearance Processing'),

    # Other
    ('Other', 'Other'),
]




RESERVABLE_STATUSES = [
    TransactionNF1.Status.COMPLETED,
    TransactionNF1.Status.CANCELLED,
    TransactionNF1.Status.ON_HOLD,
]


def random_time_between(start_hour=6, end_hour=17):
    hour = random.randint(start_hour, end_hour)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return time(hour, minute, second)


class Command(BaseCommand):
    help = 'Generate mock transactions including ON_QUEUE today.'

    def handle(self, *args, **kwargs):
        num_students = int(input("How many Student transactions to generate? "))
        num_guests = int(input("How many Guest transactions to generate? "))
        num_enrollees = int(input("How many New Enrollee transactions to generate? "))

        start_str = input("Start date (YYYY-MM-DD): ")
        end_str = input("End date (YYYY-MM-DD): ")

        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

        all_dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

        verified_users = list(User.objects.filter(verified=True))
        if not verified_users:
            print("[Warning] No verified users found.")
        else:
            print(f"[Info] Found {len(verified_users)} verified users.")

        def weighted_status_choice():
            return random.choices(
                population=[
                    TransactionNF1.Status.COMPLETED,
                    TransactionNF1.Status.CANCELLED,
                    TransactionNF1.Status.CUT_OFF,
                ],
                weights=[85, 12, 3],
                k=1
            )[0]

        def generate_for_model(model_class, count):
            population = list(model_class.objects.all())
            if not population:
                print(f"[Warning] No data for {model_class.__name__}")
                return

            for _ in range(count):
                requester = random.choice(population)
                requester.priority = random.choice([True, False])
                requester.save(update_fields=["priority"])

                txn_date = random.choice(all_dates)
                txn_time = random_time_between()
                created_at = make_aware(datetime.combine(txn_date, txn_time))

                existing = TransactionNF1.objects.filter(
                    created_at__date=txn_date,
                    student_id=requester.id if isinstance(requester, Student) else None,
                    guest_id=requester.id if isinstance(requester, Guest) else None,
                    new_enrollee_id=requester.id if isinstance(requester, NewEnrollee) else None,
                    status__in=[TransactionNF1.Status.ON_QUEUE, TransactionNF1.Status.IN_PROCESS]
                ).first()

                if existing:
                    continue

                txn_type = random.choice(TRANSACTION_TYPE)
                priority = requester.priority
                queue_number = generate_queue_number(priority)

                status = weighted_status_choice()
                reserved_by = random.choice(verified_users) if status in RESERVABLE_STATUSES and verified_users else None

                txn_nf1 = TransactionNF1.create_from_requester(
                    requester=requester,
                    transaction_type=txn_type,
                    queue_number=queue_number
                )
                txn_nf1.status = status
                txn_nf1.priority = priority
                txn_nf1.reservedBy = reserved_by
                txn_nf1.created_at = created_at
                txn_nf1.save(update_fields=["status", "priority", "reservedBy", "created_at"])

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

                print(f"Created {txn_nf1.queueNumber} ({status}, priority={priority}) for {model_class.__name__} ID {requester.pk}")

        def generate_on_queue_today(model_class, count):
            today = datetime.now().date()
            now_time = datetime.now().time()
            created_at = make_aware(datetime.combine(today, now_time))

            population = list(model_class.objects.all())
            if not population:
                print(f"[Warning] No data for {model_class.__name__}")
                return

            for _ in range(count):
                requester = random.choice(population)
                requester.priority = random.choice([True, False])
                requester.save(update_fields=["priority"])

                queue_number = generate_queue_number(requester.priority)
                txn_type = random.choice(TRANSACTION_TYPE)

                txn_nf1 = TransactionNF1.create_from_requester(
                    requester=requester,
                    transaction_type=txn_type,
                    queue_number=queue_number
                )
                txn_nf1.status = TransactionNF1.Status.ON_QUEUE
                txn_nf1.priority = requester.priority
                txn_nf1.reservedBy = None
                txn_nf1.created_at = created_at
                txn_nf1.save(update_fields=["status", "priority", "reservedBy", "created_at"])

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

                print(f"[ON_QUEUE Today] Created {txn_nf1.queueNumber} for {model_class.__name__} ID {requester.pk}")

        generate_for_model(Student, num_students)
        generate_for_model(Guest, num_guests)
        generate_for_model(NewEnrollee, num_enrollees)

        # ON_QUEUE Transactions for today
        generate_on_queue_today(Student, 20)
        generate_on_queue_today(Guest, 2)
        generate_on_queue_today(NewEnrollee, 3)

        print("✅ Done generating all transactions.")