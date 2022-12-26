from rest_framework import serializers
from services.models import *

class Service_Serializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = '__all__'
        
class Host_Serializer(serializers.ModelSerializer):
    service = Service_Serializer(read_only=True)
    location = serializers.CharField(source='location.site')
    availability = serializers.CharField(source='availability.description')
    support = serializers.CharField(source='support.hours')
    sys_admin = serializers.SerializerMethodField()
    poc_primary = serializers.SerializerMethodField()
    poc_backup = serializers.SerializerMethodField()
    class Meta:
        model = Host
        fields = ('service', 'location', 'hostname', 'ip_address',
            'qualys', 'nagios', 'syslog_standard_10514', 'syslog_relp_10515',
            'label', 'availability', 'support',
            'sys_admin', 'poc_primary', 'poc_backup', 'host_last_verified')
        
    def get_sys_admin(self, Host):
        return '{}, {}'.format(Host.sys_admin.last_name, Host.sys_admin.name)
    def get_poc_primary(self, Host):
        return '{}, {}'.format(Host.poc_primary.last_name, Host.poc_primary.name)
    def get_poc_backup(self, Host):
        return '{}, {}'.format(Host.poc_backup.last_name, Host.poc_backup.name)
