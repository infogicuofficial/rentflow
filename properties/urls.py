from django.urls import path

from . import views

app_name = "properties"

urlpatterns = [
    path("", views.rental_overview, name="overview"),
    path("flat/<int:pk>/", views.flat_detail, name="flat_detail"),
    path("occupants/", views.occupant_list, name="occupant_list"),
    path("occupants/new/", views.occupant_edit, name="occupant_new"),
    path("occupants/<int:pk>/", views.client_info, name="client_info"),
    path("occupants/<int:pk>/edit/", views.occupant_edit, name="occupant_edit"),
    path("occupancy/<int:occupancy_id>/revise-rent/", views.add_rent_revision, name="revise_rent"),
    path("occupancy/<int:occupancy_id>/toggle-notice/", views.toggle_notice, name="toggle_notice"),
]
