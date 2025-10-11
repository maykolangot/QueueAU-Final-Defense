import random
import uuid
from django.core.management.base import BaseCommand
from faker import Faker
from core.models import Student, Course
import re

CAMPUS_CHOICES = ["Main", "South", "San Jose"]
YEAR_LEVEL_CHOICES = [1, 2, 3, 4, 5]

fake = Faker('fil_PH')

def generate_qr_id():
    return str(uuid.uuid4())  # Proper UUID

class Command(BaseCommand):
    help = "Seed the database with fake Filipino students including year level and UUID QR ID"

    def add_arguments(self, parser):
        parser.add_argument('total', type=int, help='Number of fake students to create')

    def handle(self, *args, **kwargs):
        total = kwargs['total']
        courses = list(Course.objects.all())
        if not courses:
            self.stdout.write(self.style.ERROR('No courses found. Please seed departments and courses first.'))
            return

        used_ids = set()  # Declare once before loop

        for _ in range(total):
            # Generate Filipino-style name
            name = fake.name()

            # ✅ Generate a unique 12-digit ID starting with '01'
            while True:
                student_id = f"01{random.randint(10**9, 10**10 - 1)}"
                if student_id not in used_ids and not Student.objects.filter(studentId=student_id).exists():
                    used_ids.add(student_id)
                    break

            # Convert name into an email prefix
            # e.g. "Juan Dela Cruz" → "juan.delacruz.au@phinmaed.com"
            first_name, *last_name_parts = name.split()
            last_name = "".join(last_name_parts) if last_name_parts else "student"

            # Clean up and normalize name (remove accents/symbols)
            first_name = re.sub(r'[^a-zA-Z]', '', first_name).lower()
            last_name = re.sub(r'[^a-zA-Z]', '', last_name).lower()

            # Use last two digits of student_id for uniqueness
            unique_suffix = str(student_id)[-2:]

            # Build realistic student email
            email_prefix = f"{first_name}.{last_name}{unique_suffix}"
            email = f"{email_prefix}.au@phinmaed.com"



            # Weighted campus distribution
            campus = random.choices(
                population=["South", "Main", "San Jose"],
                weights=[85, 14, 1],
                k=1
            )[0]

            course = random.choice(courses)
            year_level = random.choice(YEAR_LEVEL_CHOICES)

            # Create the student record
            student = Student.objects.create(
                name=name,
                studentId=student_id,
                email=email,
                roles='student',
                campus=campus,
                course=course,
                year_level=year_level,
                qrId=generate_qr_id()
            )

            self.stdout.write(self.style.SUCCESS(f"Created student {student} ({email})"))

# To run, 
# 
#       python ./manage.py student_seeder x
# 
# 
# Where x is the number of student to be generated
