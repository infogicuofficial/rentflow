from django.contrib import admin

from .models import Building, Document, Flat, Level, Occupancy, Occupant, RentRevision


class LevelInline(admin.TabularInline):
    model = Level
    extra = 0


class FlatInline(admin.TabularInline):
    model = Flat
    extra = 0


class RevisionInline(admin.TabularInline):
    model = RentRevision
    extra = 0


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "address")
    inlines = [LevelInline]


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("building", "number", "name")
    inlines = [FlatInline]


@admin.register(Flat)
class FlatAdmin(admin.ModelAdmin):
    list_display = ("__str__", "unit_type", "size_sqft", "base_rent")
    list_filter = ("unit_type", "level__building")


@admin.register(Occupant)
class OccupantAdmin(admin.ModelAdmin):
    list_display = ("full_name", "occupant_id", "email", "phone")
    search_fields = ("full_name", "occupant_id", "email")


@admin.register(Occupancy)
class OccupancyAdmin(admin.ModelAdmin):
    list_display = ("occupant", "flat", "start_date", "rent_amount",
                    "security_deposit", "deposit_balance", "notice_given", "is_active")
    list_filter = ("is_active", "notice_given")
    inlines = [RevisionInline]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "doc_type", "occupant", "uploaded_at")
