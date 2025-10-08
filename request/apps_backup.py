"""

import os
from django.apps import AppConfig
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.utils.timezone import now
from django.db import transaction
from datetime import timedelta
import pytz

MANILA_TZ = pytz.timezone("Asia/Manila")


def process_scheduled_cutoffs():
    from core.models import CutoffSchedule, TransactionNF1, Transaction
    from django.db.models import Q

    # Get current local time in Asia/Manila
    local_now = now().astimezone(MANILA_TZ)
    print(f"[JOB] Local time (Asia/Manila): {local_now.isoformat()}")

    # Get all non-cutoff schedules
    all_pending = CutoffSchedule.objects.filter(is_cutoff=False)
    print("[DEBUG] All non-cutoff schedules:")

    for row in all_pending:
        # Convert UTC cutoff_time to Manila for comparison
        cutoff_time_local = row.cutoff_time.astimezone(MANILA_TZ)
        overdue = cutoff_time_local <= local_now

        print(
            f"→ ID {row.id} — cutoff_time (PH): {cutoff_time_local.strftime('%Y-%m-%d %H:%M:%S')} "
            f"— now: {local_now.strftime('%Y-%m-%d %H:%M:%S')} — overdue: {overdue}"
        )

    # Compare in UTC since DB is in UTC
    overdue = all_pending.filter(cutoff_time__lte=local_now.astimezone(pytz.UTC))
    print(f"[JOB] Found {overdue.count()} overdue cutoffs...")

    for sched in overdue:
        print(f"[▶] Processing overdue cutoff ID {sched.id} @ {sched.cutoff_time} (Campus: {sched.campus or 'All'})")

        with transaction.atomic():
            updated = CutoffSchedule.objects.filter(pk=sched.id, is_cutoff=False).update(is_cutoff=True)
            if updated:
                print(f"[✓] Marked CutoffSchedule ID {sched.id} as is_cutoff=True ✅")
            else:
                print(f"[⚠] Failed to mark CutoffSchedule ID {sched.id} as cutoff")

        cutoff_date = sched.cutoff_time.astimezone(MANILA_TZ).date()

        nf1_qs = TransactionNF1.objects.filter(
            status__in=[TransactionNF1.Status.ON_QUEUE, TransactionNF1.Status.ON_HOLD],
            created_at__date=cutoff_date
        )
        legacy_qs = Transaction.objects.filter(
            status__in=[Transaction.Status.ON_QUEUE, Transaction.Status.ON_HOLD],
            created_at__date=cutoff_date
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


def process_daily_hard_cutoff():
    from core.models import TransactionNF1, Transaction

    now_local = now().astimezone(MANILA_TZ)
    today = now_local.date()

    print(f"[AUTO] 5PM Hard Cutoff Triggered @ {now_local.isoformat()}")

    nf1_updated = TransactionNF1.objects.filter(
        status__in=[TransactionNF1.Status.ON_QUEUE, TransactionNF1.Status.ON_HOLD],
        created_at__date=today
    ).update(status=TransactionNF1.Status.CUT_OFF)

    legacy_updated = Transaction.objects.filter(
        status__in=[Transaction.Status.ON_QUEUE, Transaction.Status.ON_HOLD],
        created_at__date=today
    ).update(status=Transaction.Status.CUT_OFF)

    print(f"[✓ AUTO] Hard Cutoff Applied — NF1: {nf1_updated}, Legacy: {legacy_updated}")


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
            trigger=CronTrigger(hour=17, minute=0),
            id='daily_hard_cutoff',
            name='Daily Hard Cutoff at 17:00',
            replace_existing=True,
        )

        scheduler.start()
        print("[Scheduler] Jobs started and active")


"""