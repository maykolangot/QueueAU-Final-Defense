from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password



# Departments offered in the university
DEPARTMENT_CHOICES = [
    ("Engineering", "Engineering"),
    ("Information and Computing Sciences", "Information and Computing Sciences"),
    ("Business and Accountancy", "Business and Accountancy"),
    ("Arts and Sciences", "Arts and Sciences"),
    ("Education", "Education"),
    ("Nursing", "Nursing"),
    ("Architecture and Fine Arts", "Architecture and Fine Arts"),
    ("Agriculture and Forestry", "Agriculture and Forestry"),
    ("Law", "Law"),
    ("Medicine", "Medicine"),
    ("Health Sciences", "Health Sciences"),
    ("Hospitality and Tourism Management", "Hospitality and Tourism Management"),
    ("Criminal Justice Education", "Criminal Justice Education"),
    ("Social Work and Community Development", "Social Work and Community Development"),
]

# All undergraduate courses available
COURSE_CHOICES = [
    ("BS Civil Engineering", "BS Civil Engineering"),
    ("BS Mechanical Engineering", "BS Mechanical Engineering"),
    ("BS Electrical Engineering", "BS Electrical Engineering"),
    ("BS Electronics and Communications Engineering", "BS Electronics and Communications Engineering"),
    ("BS Chemical Engineering", "BS Chemical Engineering"),
    ("BS Computer Science", "BS Computer Science"),
    ("BS Information Technology", "BS Information Technology"),
    ("BS Information Systems", "BS Information Systems"),
    ("BS Software Engineering", "BS Software Engineering"),
    ("BS Business Administration (Major in Marketing Management)", "BS Business Administration (Marketing Management)"),
    ("BS Business Administration (Major in Financial Management)", "BS Business Administration (Financial Management)"),
    ("BS Accountancy", "BS Accountancy"),
    ("BS Entrepreneurship", "BS Entrepreneurship"),
    ("BS Management Accounting", "BS Management Accounting"),
    ("AB Psychology", "AB Psychology"),
    ("AB Political Science", "AB Political Science"),
    ("AB English Studies", "AB English Studies"),
    ("AB History", "AB History"),
    ("BS Biology", "BS Biology"),
    ("BS Chemistry", "BS Chemistry"),
    ("BS Mathematics", "BS Mathematics"),
    ("BSEd English", "BSEd English"),
    ("BSEd Mathematics", "BSEd Mathematics"),
    ("BSEd Science", "BSEd Science"),
    ("BS Early Childhood Education", "BS Early Childhood Education"),
    ("BS Nursing", "BS Nursing"),
    ("BS Architecture", "BS Architecture"),
    ("BS Interior Design", "BS Interior Design"),
    ("BS Fine Arts (major in Painting, Sculpture, or Multimedia Arts)", "BS Fine Arts"),
    ("BS Agriculture", "BS Agriculture"),
    ("BS Agricultural Engineering", "BS Agricultural Engineering"),
    ("BS Forestry", "BS Forestry"),
    ("Bachelor of Laws (LLB)", "Bachelor of Laws (LLB)"),
    ("Juris Doctor (JD)", "Juris Doctor (JD)"),
    ("Doctor of Medicine (MD)", "Doctor of Medicine (MD)"),
    ("BS Medical Technology", "BS Medical Technology"),
    ("BS Radiologic Technology", "BS Radiologic Technology"),
    ("BS Physical Therapy", "BS Physical Therapy"),
    ("BS Occupational Therapy", "BS Occupational Therapy"),
    ("BS Hospitality Management", "BS Hospitality Management"),
    ("BS Tourism Management", "BS Tourism Management"),
    ("BS Criminology", "BS Criminology"),
    ("BS Social Work", "BS Social Work"),
]


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
    department = models.CharField(max_length=120, default='CAS')
    qrId = models.CharField(max_length=100, unique=True)
    priority = models.BooleanField(default=False)
    campus = models.CharField("Campus", max_length=100,choices=CAMPUS_CHOICES,default="South")

    course = models.CharField(max_length=120)
    dateCreated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.roles} - {self.pk}"


class Guest(models.Model):
    roles = models.CharField("Role", max_length=10, default='Guest')
    department = models.CharField(max_length=120)
    qrId = models.CharField(max_length=100, unique=True)
    priority = models.BooleanField(default=False)
    campus = models.CharField(max_length=100, default='SOUTH')
    course = models.CharField(max_length=120)
    dateCreated = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.roles} - {self.pk}"


class Student(models.Model):
    name = models.CharField("Student Name", max_length=120)
    studentId = models.PositiveBigIntegerField(unique=True)
    email = models.EmailField("Email Address", unique=True)
    roles = models.CharField("Role", max_length=10, default='student')

    # Using choice fields for department and course
    department = models.CharField(
        "Department",
        max_length=120,
        choices=DEPARTMENT_CHOICES,
        default=DEPARTMENT_CHOICES[0][0]
    )
    course = models.CharField(
        "Course",
        max_length=120,
        choices=COURSE_CHOICES,
        default=COURSE_CHOICES[0][0]
    )

    campus = models.CharField("Campus", max_length=100)
    qrId = models.CharField("QR Identifier", max_length=100, unique=True)
    dateCreated = models.DateTimeField(auto_now_add=True)

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

    queueNumber = models.CharField(max_length=10)
    transactionType = models.CharField(max_length=100)
    status = models.CharField(
        max_length=50,
        choices=Status.choices,
        default=Status.ON_QUEUE
    )
    priority = models.BooleanField(default=False)
    onHoldCount = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=False)


    reservedBy = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE)

    # Generic foreign key to support Student, NewEnrollee, Guest
    requester_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    requester_id = models.PositiveIntegerField(null=True, blank=True)
    requestedBy = GenericForeignKey('requester_type', 'requester_id')

    def clean(self):
        allowed_models = [Student, NewEnrollee, Guest]

        if self.requester_type is None or self.requester_id is None:
            raise ValidationError("Requester must be set")

        if self.requester_type.model_class() not in allowed_models:
            raise ValidationError("Requester must be a Student, NewEnrollee, or Guest")


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

    queueNumber = models.CharField(max_length=10, unique=True, db_index=True)
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
    student = models.ForeignKey(Student, null=True, blank=True, on_delete=models.CASCADE, related_name='transactions')
    new_enrollee = models.ForeignKey(NewEnrollee, null=True, blank=True, on_delete=models.CASCADE, related_name='transactions')
    guest = models.ForeignKey(Guest, null=True, blank=True, on_delete=models.CASCADE, related_name='transactions')

    # Denormalized for easy access/filtering
    department = models.CharField(max_length=120, choices=DEPARTMENT_CHOICES)
    course = models.CharField(max_length=120, choices=COURSE_CHOICES)
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
        constraints = [
            models.UniqueConstraint(fields=['queueNumber'], name='unique_queue_number')
        ]
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
            department=requester.department,
            course=requester.course,
            campus=requester.campus
        )
