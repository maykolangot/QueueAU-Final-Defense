from django.contrib import admin
from .models import Student
from .models import Transaction
from .models import User
from .models import Guest
from .models import NewEnrollee
from .models import TransactionNF1
from .models import Department
from .models import Course
from .models import QueueState

# Register your models here.

admin.site.register(Student)
admin.site.register(Transaction)
admin.site.register(User)
admin.site.register(Guest)
admin.site.register(NewEnrollee)
admin.site.register(TransactionNF1)


admin.site.register(Department)
admin.site.register(Course)
admin.site.register(QueueState)


