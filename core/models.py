from django.db import models # type: ignore
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone



CAMPUS_CHOICES = [
    ("Main", "Main"),
    ("South", "South"),
    ("San Jose", "San Jose"),
]


class User(models.Model):
    class ProcessMode(models.TextChoices):
        MIXED = "mixed", "Mixed"
        PRIORITY_ONLY = "priority_only", "Priority Only"
        STANDARD_ONLY = "standard_only", "Standard Only"

    name = models.CharField("User", max_length=50)
    email = models.EmailField("User email", unique=True)
    password = models.CharField("Password", max_length=128, default=make_password('defaultpass'))
    
    verified = models.BooleanField(default=False)
    isAdmin = models.BooleanField(default=False)
    isOnline = models.BooleanField(default=False)
    windowNum = models.PositiveSmallIntegerField("Window Number", unique=True)

    process_mode = models.CharField(
        max_length=20,
        choices=ProcessMode.choices,
        default=ProcessMode.MIXED
    )

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.name
    

class NewEnrollee(models.Model):
    roles = models.CharField("Role", max_length=10, default='New Enroll')
    qrId = models.CharField(max_length=100, unique=True)
    priority = models.BooleanField(default=False)
    campus = models.CharField("Campus", max_length=100,choices=CAMPUS_CHOICES,default="South")

    course = models.ForeignKey(
        'Course',
        on_delete=models.SET_NULL,
        null=True,
        related_name='new_enrollee_set'
    )

    dateCreated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.roles} - {self.pk}"


class Guest(models.Model):
    roles = models.CharField("Role", max_length=10, default='Guest')
    qrId = models.CharField(max_length=100, unique=True)
    priority = models.BooleanField(default=False)
    campus = models.CharField(max_length=100, default='SOUTH')


    course = models.ForeignKey(
        'Course',
        on_delete=models.SET_NULL,
        null=True,
        related_name='guest_set'
    )

    dateCreated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.roles} - {self.pk}"
    

class Department(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Course(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='courses')

    def __str__(self):
        return self.name


class Student(models.Model):
    YEAR_LEVEL_CHOICES = [(i, f'Year {i}') for i in range(1, 6)]

    name = models.CharField("Student Name", max_length=120)
    studentId = models.CharField(max_length=14, unique=True)
    email = models.EmailField("Email Address", unique=True)
    roles = models.CharField("Role", max_length=10, default='student')

    course = models.ForeignKey(
        'Course',
        on_delete=models.SET_NULL,
        null=True,
        related_name='student_set'
    )

    qr_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True)


    # STUDENT INITIATED
    priority_request = models.BooleanField(default=False)  # Student's request

    # ADMIN DECISION
    priority = models.BooleanField(default=False)          # Final approval

    campus = models.CharField("Campus", max_length=100)
    qrId = models.CharField("QR Identifier", max_length=100, unique=True)
    dateCreated = models.DateTimeField(auto_now_add=True)

    year_level = models.PositiveSmallIntegerField(
        "Year Level",
        choices=YEAR_LEVEL_CHOICES,
        default=1
    )

    def __str__(self):
        return f"{self.name} - {self.studentId}"


# models.py
class QueueState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)  # Singleton
    position = models.PositiveSmallIntegerField(default=0)  # 0–3 for P,P,S,S cycle

    def advance(self):
        self.position = (self.position + 1) % 4
        self.save()


class Transaction(models.Model):
    class Status(models.TextChoices):
        ON_QUEUE = "on_queue", "On Queue"
        IN_PROCESS = "in_process", "In Process"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        ON_HOLD = "on_hold", "On Hold"
        CUT_OFF = "cut_off", "Cut Off"
    
    class TransactionFor(models.TextChoices):
        SEM_1 = "sem_1", "Sem 1"
        SEM_2 = "sem_2", "Sem 2"
        SUMMER = "summer", "Summer"
        OFF_TERM = "off_term", "Off Term"

    transaction_for = models.CharField(
        max_length=20,
        choices=TransactionFor.choices,
        default=TransactionFor.SEM_1
    )

    queueNumber = models.CharField(max_length=10)
    transactionType = models.CharField(max_length=100)
    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.ON_QUEUE
    )
    priority = models.BooleanField(default=False)
    onHoldCount = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    reservedBy = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)

    # ✅ Direct FK fields for clean linkage
    student = models.ForeignKey(Student, null=True, blank=True, on_delete=models.CASCADE, related_name='legacy_transactions')
    new_enrollee = models.ForeignKey(NewEnrollee, null=True, blank=True, on_delete=models.CASCADE, related_name='legacy_transactions')
    guest = models.ForeignKey(Guest, null=True, blank=True, on_delete=models.CASCADE, related_name='legacy_transactions')

    def clean(self):
        references = [self.student, self.new_enrollee, self.guest]
        if sum(x is not None for x in references) != 1:
            raise ValidationError("Exactly one of student, new_enrollee, or guest must be set.")

    def get_requester(self):
        return self.student or self.new_enrollee or self.guest

    def __str__(self):
        return f"Queue {self.queueNumber} - {self.status}"


class TransactionNF1(models.Model):
    class Status(models.TextChoices):
        
        ON_QUEUE = "on_queue", "On Queue"
        IN_PROCESS = "in_process", "In Process"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        ON_HOLD = "on_hold", "On Hold"
        CUT_OFF = "cut_off", "Cut Off"
    

    class TransactionFor(models.TextChoices):
        ENROLLMENT = "enrollment","Enrollment"
        SEM_1 = "sem_1", "Sem 1"
        SEM_2 = "sem_2", "Sem 2"
        SUMMER = "summer", "Summer"
        OFF_TERM = "off_term", "Off Term"

    transaction_for = models.CharField(
        max_length=20,
        choices=TransactionFor.choices,
        default=TransactionFor.SEM_1
    )

    queueNumber = models.CharField(max_length=10, db_index=True)
    transactionType = models.CharField(max_length=100)
    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.ON_QUEUE,
        db_index=True
    )
    priority = models.BooleanField(default=False)
    onHoldCount = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    reservedBy = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE, related_name='reserved_transactions')

    # Normalized ForeignKeys (only one active)
    student = models.ForeignKey(Student, null=True, blank=True, on_delete=models.CASCADE, related_name='nf1_transactions')
    new_enrollee = models.ForeignKey(NewEnrollee, null=True, blank=True, on_delete=models.CASCADE, related_name='nf1_transactions')
    guest = models.ForeignKey(Guest, null=True, blank=True, on_delete=models.CASCADE, related_name='nf1_transactions')


    course = models.ForeignKey(
        'Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='nf1_transactions'
    )

    campus = models.CharField(max_length=100, choices=CAMPUS_CHOICES)

    def clean(self):
        super().clean()
        references = [self.student, self.new_enrollee, self.guest]
        if sum(x is not None for x in references) != 1:
            raise ValidationError("Exactly one of student, new_enrollee, or guest must be set.")

    def get_requester(self):
        return self.student or self.new_enrollee or self.guest

    def __str__(self):
        return f"Queue {self.queueNumber} - {self.status}"

    class Meta:
        ordering = ['-created_at']
    

    @classmethod
    def create_from_requester(cls, requester, transaction_type, queue_number):
        # Identify model type
        student = requester if isinstance(requester, Student) else None
        new_enrollee = requester if isinstance(requester, NewEnrollee) else None
        guest = requester if isinstance(requester, Guest) else None

        return cls.objects.create(
            queueNumber=queue_number,
            transactionType=transaction_type,
            status=cls.Status.ON_QUEUE,
            priority=getattr(requester, 'priority', False),
            student=student,
            new_enrollee=new_enrollee,
            guest=guest,
            
            course=requester.course,
            campus=requester.campus
        )


class CutoffSchedule(models.Model):

    campus = models.CharField(max_length=100, choices=CAMPUS_CHOICES, blank=True, null=True)  # Null = All campuses
    is_cutoff = models.BooleanField(default=False)  # True = action triggered
    cutoff_time = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-cutoff_time']

    def __str__(self):
        return f"Cutoff at {self.cutoff_time.strftime('%Y-%m-%d %H:%M:%S')} for {'All' if not self.campus else self.campus}"
    
    

import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta

class TwoFactorToken(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=10)

    def __str__(self):
        return f"2FA token for {self.user.email} ({self.token})"
