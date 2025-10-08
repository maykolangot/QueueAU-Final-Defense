from django import forms
from core.models import Student, NewEnrollee, Guest, Department, Course, User
from django.core.validators import RegexValidator
from django.contrib.auth.hashers import make_password



class StudentRegistrationForm(forms.ModelForm):
    CAMPUS_CHOICES = [
        ('Main', 'Main'),
        ('South', 'South'),
        ('San Jose', 'San Jose'),
    ]

    YEAR_LEVEL_CHOICES = [(i, f'Year {i}') for i in range(1, 6)]

    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        empty_label="Select Department",
        required=True
    )
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),
        empty_label="Select Course",
        required=True
    )
    campus = forms.ChoiceField(
        choices=[('', 'Select Campus')] + CAMPUS_CHOICES,
        required=True
    )
    year_level = forms.ChoiceField(
        choices=[('', 'Select Year Level')] + YEAR_LEVEL_CHOICES,
        required=True,
        label="Year Level"
    )
    priority_request = forms.BooleanField(
        required=False,
        label="Request Priority",
        help_text="Check if you would like to request priority consideration (e.g., for interviews)."
    )

    class Meta:
        model = Student
        fields = [
            'name',
            'studentId',   # ⚠️ Ensure model field matches this name
            'email',
            'department',
            'course',
            'campus',
            'year_level',
            'priority_request',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dynamically load courses based on department
        if 'department' in self.data:
            try:
                department_id = int(self.data.get('department'))
                self.fields['course'].queryset = Course.objects.filter(
                    department_id=department_id
                ).order_by('name')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and hasattr(self.instance, 'department'):
            self.fields['course'].queryset = Course.objects.filter(
                department=self.instance.department
            )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and not email.endswith('@phinmaed.com'):
            raise forms.ValidationError("Only @phinmaed.com emails are allowed.")
        return email

    def clean_studentId(self):
        """Normalize studentId by removing dashes"""
        student_id = self.cleaned_data.get('studentId')
        if student_id:
            student_id_str = str(student_id)  # Ensure string before replace
            return student_id_str.replace("-", "")
        return student_id

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        student_id = cleaned_data.get("studentId")

        # Unique email (ignore self when editing)
        if email and Student.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            self.add_error("email", "This email is already registered.")

        # Unique student ID (ignore self when editing)
        if student_id and Student.objects.filter(studentId=student_id).exclude(pk=self.instance.pk).exists():
            self.add_error("studentId", "This ID number is already registered.")

        return cleaned_data

class NewEnrolleeForm(forms.ModelForm):
    class Meta:
        model = NewEnrollee
        fields = ['priority', 'campus']


class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = ['priority', 'campus']



TRANSACTION_TYPE_CHOICES = [
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



TRANSACTION_FOR_CHOICES = [
    ('enrollment', 'Enrollment'),
    ('sem_1', 'Sem 1'),
    ('sem_2', 'Sem 2'),
    ('summer', 'Summer'),
    ('off_term', 'Off Term'),
]


UUID_REGEX = (
    r'^[0-9a-fA-F]{8}-'
    r'[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{12}$'
)

class QueueRequestForm(forms.Form):
    qrId = forms.CharField(
        label="Scan or Enter QR ID",
        min_length=36,
        max_length=36,
        validators=[
            RegexValidator(
                regex=UUID_REGEX,
                message="Enter a valid UUID (e.g. 6c90f095-a5ca-4f5f-a61b-c882eaf5cece)"
            )
        ],
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Please, scan your QR code',
            'maxlength': '36',
            'pattern': '[0-9a-fA-F\\-]{36}',
            'title': 'Must be exactly 36 characters (UUID format)'
        })
    )


    transaction_for = forms.ChoiceField(
        choices=[('', '-- Select Transaction For --')] + TRANSACTION_FOR_CHOICES,
        label="Transaction For",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    transactionType = forms.ChoiceField(
        choices=[('', '-- Select Transaction Type --')] + TRANSACTION_TYPE_CHOICES,
        label="Select Transaction Type",
        widget=forms.Select(attrs={'class': 'form-select'})
    )



from django.db.models import Max
import re


class RegisterUser(forms.ModelForm):
    name = forms.CharField(label="Name")
    email = forms.EmailField(label="Email")

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ['name', 'email']

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email.endswith('@phinmaed.com'):
            raise forms.ValidationError("Email must be a @phinmaed.com address.")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists.")
        return email

    def clean_password1(self):
        password = self.cleaned_data.get("password1")

        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r'[a-z]', password):
            raise forms.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r'\d', password):
            raise forms.ValidationError("Password must contain at least one number.")
        if not re.search(r'[^\w\s]', password):
            raise forms.ValidationError("Password must contain at least one special character.")

        return password

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])

        # Safely assign windowNum
        if not user.windowNum:
            last_window = User.objects.aggregate(max_win=Max('windowNum'))['max_win'] or 0
            user.windowNum = last_window + 1

        if commit:
            user.save()
        return user
    

    