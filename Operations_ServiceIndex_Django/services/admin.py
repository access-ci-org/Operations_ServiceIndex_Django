from django.contrib import admin
from services.models import *

# Register your models here.

class StaffAdmin(admin.ModelAdmin):
    list_display = ('name', 'last_name', 'email')
    list_display_links = ['name']
    ordering = ['name']
    search_fields = ['name', 'last_name', 'email']
admin.site.register(Staff, StaffAdmin)

class SiteAdmin(admin.ModelAdmin):
    list_display = ('site',)
    list_display_links = ['site']
    ordering = ['site']
    search_fields = ['site']
admin.site.register(Site, SiteAdmin)

class SupportAdmin(admin.ModelAdmin):
    list_display = ('hours',)
    list_display_links = ['hours']
    ordering = ['hours']
    search_fields = ['hours']
admin.site.register(Support, SupportAdmin)

class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ('tier', 'description')
    list_display_links = ['tier']
    ordering = ['tier']
    search_fields = ['tier']
admin.site.register(Availability, AvailabilityAdmin)

class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'hostname', 'deprecated')
    list_display_links = ['name']
    ordering = ['name']
    search_fields = ['name', 'hostname']
admin.site.register(Service, ServiceAdmin)

class HostAdmin(admin.ModelAdmin):
    list_display = ('service', 'location', 'hostname', 'label')
    list_display_links = ['service']
    ordering = ['service']
    search_fields = ['service', 'hostname']
admin.site.register(Host, HostAdmin)

class LinkAdmin(admin.ModelAdmin):
    list_display = ('service', 'url')
    list_display_links = ['service']
    ordering = ['service']
    search_fields = ['service', 'url']
admin.site.register(Link, LinkAdmin)

class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('service', 'username', 'timestamp')
    list_display_links = ['service']
    ordering = ['timestamp']
    search_fields = ['service', 'username']
admin.site.register(LogEntry, LogEntryAdmin)

class EditLockAdmin(admin.ModelAdmin):
    list_display = ('service', 'username', 'timestamp')
    list_display_links = ['service']
    ordering = ['timestamp']
    search_fields = ['service', 'username']
admin.site.register(EditLock, EditLockAdmin)

class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')
    list_display_links = ['name']
    ordering = ['created']
    search_fields = ['name']
admin.site.register(Event, EventAdmin)

class HostEventStatusAdmin(admin.ModelAdmin):
    list_display = ('event', 'host', 'status')
    list_display_links = ['event']
    ordering = ['event', 'host']
    search_fields = ['event', 'host']
admin.site.register(HostEventStatus, HostEventStatusAdmin)

class HostEventLogAdmin(admin.ModelAdmin):
    list_display = ('event', 'host', 'timestamp')
    list_display_links = ['event']
    ordering = ['timestamp']
    search_fields = ['event', 'host']
admin.site.register(HostEventLog, HostEventLogAdmin)

class Misc_urlsAdmin(admin.ModelAdmin):
    list_display = ('name',)  # tag loc list
    search_fields = ('urls',)
admin.site.register(Misc_urls, Misc_urlsAdmin)
