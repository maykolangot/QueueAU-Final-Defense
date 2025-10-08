from django.urls import path
from . import views

urlpatterns = [
    path('login_user/', views.login_user, name='login'),
    path('2fa/<uuid:token>/', views.verify_2fa_uuid, name='verify_2fa_uuid'),

    path('cashier/', views.cashier_dashboard_content, name='cashier'),
    path('dashboard/data/', views.cashier_dashboard_data, name='cashier_dashboard_data'),
    path('app-logout/', views.logout_user, name='logout'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<str:token>/', views.reset_password, name='reset_password'),


    # Dashboard
   # path('dashboard/upcoming/', views.get_upcoming_queues, name='get_upcoming_queues'),
    path("cashier/print-transactions/", views.print_cashier_transactions, name="print_cashier_transactions"),
    # urls.py
    path('department-list/', views.department_list, name='department_list'),
    path('course-list/', views.course_list, name='course_list'),


    path("cashier/forecast-chart-data/", views.forecast_chart_data, name="forecast_chart_data"),



    # Dashboard buttons
    path('dashboard/next/', views.next_queue, name='next_queue'),
    path('dashboard/skip/', views.skip_queue, name='skip_queue'),
    path('dashboard/current/', views.get_current_queue, name='get_current_queue'),
    path('dashboard/hold/', views.hold_queue, name='hold_queue'),

    # urls.py
    path('dashboard/next-queues/', views.next_queues_list, name='next_queues_list'),


    # new hold with csrf
    path('dashboard/hold-queue/', views.hold_queue, name='hold_queue'),


    path('dashboard/holds/', views.list_on_hold_transactions, name='list_on_hold_transactions'),
    path('dashboard/holds/update/', views.update_hold_status, name='update_hold_status'),




    # User Profile
    path('content/', views.cashier_profile_content, name='cashier_profile_content'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),

    # User Settings
    path('settings/content/', views.cashier_settings_content, name='cashier_settings_content'),



    # Admin Navigation Bar
    path('admin/dashboard/dashboard_summary/', views.admin_dashboard_summary, name='admin_dashboard_summary'),



    # Statistics Emeruts:
    path("admin/dashboard/statistics/", views.admin_statistics, name="admin_statistics"),
    path("admin/dashboard/statistics/data/", views.statistics_data, name="statistics_data"),
    path("admin/dashboard/statistics/transaction-types/", views.transaction_type_chart_data, name="transaction_type_chart_data"),
    path("admin/dashboard/statistics/status-donut/", views.status_donut_chart_data, name="status_donut_chart_data"),
    path("admin/dashboard/statistics/status-by-department/", views.status_by_department_chart_data, name="status_by_department_chart_data"),
    
    path("admin/dashboard/statistics/priority-breakdown/", views.priority_breakdown_view, name="priority_breakdown_view"),
    path("admin/dashboard/statistics/heatmap-time/", views.heatmap_chart_data, name='heatmap_chart_data'),
    path("admin/dashboard/statistics/heatmap-hourly/", views.hourly_heatmap_chart_data, name="hourly_heatmap_chart_data"),
    path("admin/dashboard/statistics/forecast/", views.forecast_chart_data, name="forecast_chart_data"),
    path("admin/dashboard/statistics/avg-processing-time/", views.average_processing_time_view, name="average_processing_time_view"),
    path("admin/dashboard/statistics/sem-tx-grouped/", views.sem_transaction_type_grouped_chart, name="sem_transaction_type_grouped_chart"),




    path("admin/dashboard/statistics/print/", views.generate_transaction_pdf, name="transaction_report_pdf"),



    path('admin/dashboard/statistics/api/departments/', views.department_list, name='api-departments'),
    path('admin/dashboard/statistics/api/courses/',     views.course_list,     name='api-courses'),



    

    path('ajax/get-courses/', views.get_courses_by_department, name='get_courses_by_department'),




    # verified and non verified
    # Cashier Transaction

    path("admin/dashboard/cashiers/list/", views.cashier_list_view, name="cashier_list"),
    path("admin/dashboard/cashiers/verify/<int:cashier_id>/", views.verify_cashier, name="cashier_verify"),
    path("admin/dashboard/cashiers/reject/<int:cashier_id>/", views.reject_cashier, name="cashier_reject"),

    path("admin/dashboard/cashiers/list/<int:cashier_id>/transactions/", views.cashier_transactions_view, name="cashier_transactions"),
    path("admin/dashboard/cashiers/list/<int:cashier_id>/edit/", views.cashier_update_view, name="cashier_update"),
    path("admin/dashboard/cashiers/list/<int:cashier_id>/delete/", views.cashier_delete_view, name="cashier_delete"),
    path('admin/dashboard/cashiers/list/<int:cashier_id>/transactions/pdf/', views.cashier_transactions_pdf_view, name='cashier_transactions_pdf'),







    path("admin/dashboard/search/", views.student_list_view, name="student_list"),
    path("admin/students/update-priority/", views.update_priority_requests, name="update_priority_requests"),
    path("admin/dashboard/search/<int:student_id>/transactions/", views.student_transactions_ajax, name="student_transactions_ajax"),




    path('admin/dashboard/queue_settings/', views.admin_queue_settings, name='admin_queue_settings'),

    path('admin/dashboard/logs/', views.log_viewer, name='log_viewer'),



    # Key performance Indicator
    path('admin/dashboard/dashboard_summary/kpi-data/', views.kpi_data, name='kpi-data'),
    path('admin/dashboard/kpi-data/', views.kpi_data, name='kpi-data'),
    path('admin/dashboard/dashboard_summary/kpi-cashier/', views.kpi_summary, name='kpi-cashier'),


]   
