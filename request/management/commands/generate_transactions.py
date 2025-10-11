import random
from datetime import datetime, timedelta, time

from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware

from core.models import (
    Student, Guest, NewEnrollee,
    TransactionNF1, Transaction,
    User
)
from request.views import generate_queue_number


TRANSACTION_TYPES = ["Enrollment", "Inquiry", "Payment"]
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
    help = 'Generate mock transactions for Students, Guests, and New Enrollees'

    def handle(self, *args, **kwargs):
        num_students = int(input("How many Student transactions to generate? "))
        num_guests = int(input("How many Guest transactions to generate? "))
        num_enrollees = int(input("How many New Enrollee transactions to generate? "))

        start_str = input("Start date (YYYY-MM-DD): ")
        end_str = input("End date (YYYY-MM-DD): ")

        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

        all_dates = [
            start_date + timedelta(days=i)
            for i in range((end_date - start_date).days + 1)
        ]

        users = list(User.objects.all())
        if not users:
            print("⚠️ No users found to assign as reservedBy.")
        else:
            print(f"ℹ️ Found {len(users)} users for potential reservedBy assignment.")

        def generate_for_model(model_class, count):
            population = list(model_class.objects.all())
            if not population:
                print(f"No data found for {model_class.__name__}")
                return

            for _ in range(count):
                requester = random.choice(population)

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

                txn_type = random.choice(TRANSACTION_TYPES)
                priority = getattr(requester, 'priority', False)
                queue_number = generate_queue_number(priority)

                # Randomly choose a status
                status_choices = list(TransactionNF1.Status)
                status = random.choice(status_choices)

                # Optional: reservedBy for some statuses
                reserved_by = random.choice(users) if status in RESERVABLE_STATUSES and users else None

                # Create TransactionNF1
                txn_nf1 = TransactionNF1.create_from_requester(
                    requester=requester,
                    transaction_type=txn_type,
                    queue_number=queue_number
                )
                txn_nf1.status = status
                txn_nf1.reservedBy = reserved_by
                txn_nf1.created_at = created_at
                txn_nf1.save(update_fields=["status", "reservedBy", "created_at"])

                # Create legacy Transaction
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

                print(f"✅ Created {txn_nf1.queueNumber} ({status}) for {model_class.__name__} ID {requester.pk}")

        generate_for_model(Student, num_students)
        generate_for_model(Guest, num_guests)
        generate_for_model(NewEnrollee, num_enrollees)

        print("🎉 Finished generating mock transactions.")
