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
    'Downpayment',
    'Miscellaneous',
    'Payment',
    'P1',
    'P2',
    'P3',
    'INC Completion',
    'Registration Fee',
    'Laboratory Fee',
    'Library Fee',
    'ID Replacement Fee',
    'Graduation Fee',
    'Certificate Issuance Fee',
    'Transcript of Records Request',
    'Diploma Request',
    'Late Enrollment Penalty',
    'Miscellaneous Fee',
    'Workshop Fee',
    'Seminar Fee',
    'Continuing Education',
    'Subject Overload Request',
    'Subject Withdrawal',
    'Cross Enrollment',
    'Shifting Request',
    'Leave of Absence',
    'Reinstatement Request',
    'Change of Schedule',
    'Good Moral Certificate',
    'Honorable Dismissal',
    'Course Description Request',
    'Enrollment Verification',
    'Student Copy of Grades',
    'English Proficiency Certificate',
    'Student Portal Issue',
    'ID Application',
    'RFID Access Request',
    'Scholarship Application',
    'Payment Discrepancy',
    'Clearance Processing',
    'Other',
]

TRANSACTION_FOR_CHOICES = ['sem_1', 'sem_2', 'summer', 'off_term']

#  TRANSACTION_FOR_CHOICES = ['sem_1', 'sem_2', 'summer', 'off_term']

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

        queue_counter = {}

        def get_queue_number(date_key, is_priority):
            prefix = "P" if is_priority else "S"
            key = f"{date_key}_{prefix}"
            queue_counter[key] = queue_counter.get(key, 0) + 1
            return f"{prefix}-{str(queue_counter[key]).zfill(4)}"



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
        

        
        def weighted_transaction_type_choice():
            weights = []
            for t in TRANSACTION_TYPE:
                if t == 'P1':
                    weights.append(95)
                else:
                    weights.append(5 / (len(TRANSACTION_TYPE) - 1))
            return random.choices(TRANSACTION_TYPE, weights=weights, k=1)[0]



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

                txn_type = weighted_transaction_type_choice()
                txn_for = random.choice(TRANSACTION_FOR_CHOICES)
                priority = requester.priority
                queue_number = get_queue_number(txn_date, priority)
                status = weighted_status_choice()
                reserved_by = random.choice(verified_users) if status in RESERVABLE_STATUSES else None

                txn_nf1 = TransactionNF1.create_from_requester(requester, txn_type, queue_number)
                txn_nf1.transaction_for = txn_for
                txn_nf1.status = status
                txn_nf1.priority = priority
                txn_nf1.reservedBy = reserved_by
                txn_nf1.created_at = created_at
                txn_nf1.save(update_fields=["transaction_for", "status", "priority", "reservedBy", "created_at"])

                Transaction.objects.create(
                    queueNumber=txn_nf1.queueNumber,
                    transactionType=txn_nf1.transactionType,
                    transaction_for=txn_for,
                    status=txn_nf1.status,
                    priority=txn_nf1.priority,
                    onHoldCount=txn_nf1.onHoldCount,
                    created_at=txn_nf1.created_at,
                    reservedBy=txn_nf1.reservedBy,
                    student=txn_nf1.student,
                    new_enrollee=txn_nf1.new_enrollee,
                    guest=txn_nf1.guest,
                )

                print(f"Created {txn_nf1.queueNumber} ({status}, {txn_for}, priority={priority}) for {model_class.__name__} ID {requester.pk}")

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

                queue_number = get_queue_number(today, requester.priority)
                txn_type = weighted_transaction_type_choice()

                txn_for = random.choice(TRANSACTION_FOR_CHOICES)

                txn_nf1 = TransactionNF1.create_from_requester(requester, txn_type, queue_number)
                txn_nf1.transaction_for = txn_for
                txn_nf1.status = TransactionNF1.Status.ON_QUEUE
                txn_nf1.priority = requester.priority
                txn_nf1.reservedBy = None
                txn_nf1.created_at = created_at
                txn_nf1.save(update_fields=["transaction_for", "status", "priority", "reservedBy", "created_at"])

                Transaction.objects.create(
                    queueNumber=txn_nf1.queueNumber,
                    transactionType=txn_nf1.transactionType,
                    transaction_for=txn_for,
                    status=txn_nf1.status,
                    priority=txn_nf1.priority,
                    onHoldCount=txn_nf1.onHoldCount,
                    created_at=txn_nf1.created_at,
                    reservedBy=txn_nf1.reservedBy,
                    student=txn_nf1.student,
                    new_enrollee=txn_nf1.new_enrollee,
                    guest=txn_nf1.guest,
                )

                print(f"[ON_QUEUE Today] Created {txn_nf1.queueNumber} ({txn_for}) for {model_class.__name__} ID {requester.pk}")

        generate_for_model(Student, num_students)
        generate_for_model(Guest, num_guests)
        generate_for_model(NewEnrollee, num_enrollees)

        generate_on_queue_today(Student, 20)
        generate_on_queue_today(Guest, 2)
        generate_on_queue_today(NewEnrollee, 3)

        print("✅ Done generating all transactions.")

