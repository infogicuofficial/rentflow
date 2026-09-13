from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("", views.payment_main, name="main"),
    path("new/", views.make_payment, name="make_payment"),
    path("manage/", views.manage_payments, name="manage"),
    path("confirmation/<int:invoice_id>/", views.payment_confirmation, name="confirmation"),
    path("invoice/<int:invoice_id>/resend/", views.resend_invoice, name="resend_invoice"),
    path("payment/<int:payment_id>/delete/", views.delete_payment, name="delete_payment"),
    # portal API
    path("api/flats/", views.api_flats, name="api_flats"),
    path("api/flat-context/", views.api_flat_context, name="api_flat_context"),
    path("api/verify/", views.api_verify, name="api_verify"),
    path("api/generate-invoice/", views.api_generate_invoice, name="api_generate_invoice"),
]
