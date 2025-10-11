import os
from django.apps import AppConfig
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from django.utils.timezone import now

from datetime import timedelta
import pytz

MANILA_TZ = pytz.timezone("Asia/Manila")


def process_scheduled_cutoffs():
    from core.models import CutoffSchedule, TransactionNF1, Transaction
    from django.db.models import Q
    from django.db import transaction

    local_now = now().astimezone(MANILA_TZ)
    print(f"[JOB] Local time (Asia/Manila): {local_now.isoformat()}")

    overdue = CutoffSchedule.objects.filter(
        is_cutoff=False,
        cutoff_time__lte=local_now.astimezone(pytz.UTC)
    )

    print(f"[JOB] Found {overdue.count()} overdue cutoffs...")

    for sched in overdue:
        cutoff_time_local = sched.cutoff_time.astimezone(MANILA_TZ)
        campus_name = sched.campus or "All"

        print(f"[▶] Processing overdue cutoff ID {sched.id} @ {cutoff_time_local:%Y-%m-%d %H:%M:%S} (Campus: {campus_name})")

        with transaction.atomic():
            updated = CutoffSchedule.objects.filter(pk=sched.id, is_cutoff=False).update(is_cutoff=True)
            if not updated:
                print(f"[⚠] Skipped cutoff ID {sched.id} — already marked")
                continue

        print(f"[✓] Marked CutoffSchedule ID {sched.id} as is_cutoff=True ✅")

        # Optional: mark queued transactions as CUT_OFF
        cutoff_start = cutoff_time_local.replace(tzinfo=None)
        cutoff_end = cutoff_start + timedelta(days=1)

        nf1_qs = TransactionNF1.objects.filter(
            status__in=[TransactionNF1.Status.ON_QUEUE, TransactionNF1.Status.ON_HOLD],
            created_at__gte=cutoff_start,
            created_at__lt=cutoff_end
        )

        legacy_qs = Transaction.objects.filter(
            status__in=[Transaction.Status.ON_QUEUE, Transaction.Status.ON_HOLD],
            created_at__gte=cutoff_start,
            created_at__lt=cutoff_end
        )

        if sched.campus:
            nf1_qs = nf1_qs.filter(campus=sched.campus)
            legacy_qs = legacy_qs.filter(
                Q(student__campus=sched.campus) |
                Q(new_enrollee__campus=sched.campus) |
                Q(guest__campus=sched.campus)
            )

        nf1_updated = nf1_qs.update(status=TransactionNF1.Status.CUT_OFF)
        legacy_updated = legacy_qs.update(status=Transaction.Status.CUT_OFF)

        print(f"[→] Transactions updated — NF1: {nf1_updated}, Legacy: {legacy_updated}")

    print("[✓] Scheduled cutoff job completed successfully.")



def process_daily_hard_cutoff(days_back: int = 7):
    """
    Apply daily hard cutoff at 5PM.
    If the machine was off, also catch up for the past `days_back` days.
    """
    from core.models import TransactionNF1, Transaction

    now_local = now().astimezone(MANILA_TZ)

    for days in range(0, days_back + 1):
        day = now_local.date() - timedelta(days=days)
        print(f"[AUTO] Hard Cutoff for {day} (executed @ {now_local.isoformat()})")

        nf1_updated = TransactionNF1.objects.filter(
            status__in=[TransactionNF1.Status.ON_QUEUE, TransactionNF1.Status.ON_HOLD],
            created_at__date=day
        ).update(status=TransactionNF1.Status.CUT_OFF)

        legacy_updated = Transaction.objects.filter(
            status__in=[Transaction.Status.ON_QUEUE, Transaction.Status.ON_HOLD],
            created_at__date=day
        ).update(status=Transaction.Status.CUT_OFF)

        print(f"[✓ AUTO] Hard Cutoff Applied — Date: {day}, NF1: {nf1_updated}, Legacy: {legacy_updated}")

class CoreConfig(AppConfig):
    name = 'request'  # your app name
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            print("[Scheduler] Skipped (not in main runserver thread)")
            return

        print("[Scheduler] Initializing job scheduler...")
        scheduler = BackgroundScheduler(timezone="Asia/Manila")

        scheduler.add_job(
            process_scheduled_cutoffs,
            trigger=IntervalTrigger(minutes=1),
            id='scheduled_cutoffs',
            name='Overdue Cutoff Trigger',
            replace_existing=True,
        )

        scheduler.add_job(
            process_daily_hard_cutoff,
            trigger=CronTrigger(hour=21, minute=10),
            id='daily_hard_cutoff',
            name='Daily Hard Cutoff at 17:00',
            replace_existing=True,
            kwargs={"days_back": 7},  # <- add this
        )

        scheduler.start()
        print("[Scheduler] Jobs started and active")
