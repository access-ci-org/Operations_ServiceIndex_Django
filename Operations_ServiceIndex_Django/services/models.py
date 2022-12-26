from django.db import models
from django import forms

class Staff(models.Model):
    """
    Foreign key for sys_admin, poc_primary, and poc_backup in Instance.
    """
    name = models.CharField(max_length=256)
    email = models.EmailField(max_length=256)
    phone = models.CharField(max_length=64, blank=True)
    last_name = models.CharField(max_length=64)
    deleted = models.BooleanField(default=False)
    
    def __unicode__(self):
        return self.name + ' (' + self.email + ')'
    def __str__(self):
        return '{}, {} <{}>'.format(self.last_name, self.name, self.email)

    class Meta:
        db_table = '"serviceindex"."staff"'

class Site(models.Model):
    """
    Foreign key in Instance.
    """
    site = models.CharField(max_length=256)

    def __unicode__(self):
        return self.site
    def __str__(self):
        return str(self.site)

    class Meta:
        db_table = '"serviceindex"."site"'

class Support(models.Model):
    """
    Foreign key in Instance.
    """
    hours = models.CharField(max_length=256)

    def __unicode__(self):
        return self.hours
    def __str__(self):
        return str(self.hours)

    class Meta:
        db_table = '"serviceindex"."support"'

class Availability(models.Model):
    """
    Foreign key in Instance.
    """
    tier = models.IntegerField()
    description = models.CharField(max_length=512)

    def __unicode__(self):
        return self.description
    def __str__(self):
        return '{}/{}'.format(self.tier, self.description)

    class Meta:
        db_table = '"serviceindex"."availability"'

class Service(models.Model):
    """
    Main model for a service entry.  Each Service will have one or more 
    related Instances.  Also, each Service can have 0 or more related Links.
    """
    name = models.CharField(max_length=256, unique=True)
    description = models.CharField(max_length=2048, blank=True)
    hostname = models.CharField(max_length=256, blank=True) # URL?
    failover_process = models.CharField(max_length=1024, blank=True)
    failover_last_tested = models.DateField(null=True, blank=True)
    service_last_verified = models.DateField(null=True, blank=True)
    dependencies = models.CharField(max_length=1024, blank=True)
    lb = models.BooleanField()
    ha = models.BooleanField()
    otp = models.BooleanField()
    nagios  = models.BooleanField()
    deprecated = models.BooleanField(default=False)
    # TODO  need 'last_updated' field

    def __unicode__(self):
        return self.name
    def __str__(self):
        return str(self.name)

    class Meta:
        db_table = '"serviceindex"."service"'

class Host(models.Model):
    #TYPE_CHOICES = (
    #    ('primary', 'primary'),
    #    ('secondary', 'secondary'),
    #    ('tertiary', 'tertiary'),
    #    ('prod', 'prod'),
    #    ('test', 'test'),
    #    # TODO other choices ??
    #)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    location = models.ForeignKey(Site, on_delete=models.CASCADE)
    hostname = models.CharField(max_length=256, blank=True) # multiple?
    ip_address = models.CharField(max_length=128, blank=True)
    qualys = models.BooleanField(blank=False)
    nagios = models.BooleanField(blank=False)
    syslog_standard_10514 = models.BooleanField(blank=False)
    syslog_relp_10515 = models.BooleanField(blank=False)
    #type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    label = models.CharField(max_length=128)  # 'primary', 'test', etc.
    availability = models.ForeignKey(Availability, on_delete=models.CASCADE)
    support = models.ForeignKey(Support, on_delete=models.CASCADE)
    sys_admin = models.ForeignKey(Staff, on_delete=models.CASCADE,
            related_name='sys_admin_instance_set')
    poc_primary = models.ForeignKey(Staff, on_delete=models.CASCADE,
            related_name='poc_primary_instance_set')
    poc_backup = models.ForeignKey(Staff, on_delete=models.CASCADE,
            related_name='poc_backup_instance_set')
    note = models.CharField(max_length=2048, blank=True)
    host_last_verified = models.DateField(null=True, blank=True)

    def __str__(self):
        return 'label={}:host={}:service={}'.format(self.label, self.hostname, self.service)

    class Meta:
        db_table = '"serviceindex"."host"'

class Link(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE,)
    url = models.URLField(max_length=512)
    description = models.CharField(max_length=1024)

    class Meta:
        db_table = '"serviceindex"."link"'

class EditLock(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    username = models.CharField(max_length=16)
    service = models.ForeignKey(Service, on_delete=models.CASCADE,)

    class Meta:
        db_table = '"serviceindex"."editlock"'
    

class Event(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=128)
    description = models.CharField(max_length=1024)

    def __str__(self):
        return '{} (id={})'.format(self.name, self.id)

    class Meta:
        db_table = '"serviceindex"."event"'

class HostEventStatus(models.Model):
    UNCHECKED = 'unchecked'
    IN_PROGRESS = 'in_progress'
    COMPLIANT = 'compliant'
    NA = 'na'
    STATUS_CHOICES = (
        (UNCHECKED, 'unchecked'),
        (IN_PROGRESS, 'in progress'),
        (COMPLIANT, 'compliant'),
        (NA, 'N/A'),
    )
    event = models.ForeignKey(Event, on_delete=models.CASCADE,)
    host = models.ForeignKey(Host, on_delete=models.CASCADE,)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    #note = models.CharField(max_length=1024, blank=True)
        
    class Meta:
        db_table = '"serviceindex"."hosteventstatus"'


class HostEventLog(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE,)
    host = models.ForeignKey(Host, on_delete=models.CASCADE,)
    timestamp = models.DateTimeField(auto_now_add=True)
    username = models.CharField(max_length=16)
    note = models.CharField(max_length=2048, blank=True)
    status = models.CharField(max_length=32, 
    choices=HostEventStatus.STATUS_CHOICES)
   
    class Meta:
        db_table = '"serviceindex"."hosteventlog"'
 
class LogEntry(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    username = models.CharField(max_length=16)  # the user making changes about one of the following
    service = models.ForeignKey(Service, blank=True, null=True, on_delete=models.CASCADE,)
    host = models.ForeignKey(Host, blank=True, null=True, on_delete=models.CASCADE,)
    staff = models.ForeignKey(Staff, blank=True, null=True, on_delete=models.CASCADE,)
    event = models.ForeignKey(Event, blank=True, null=True, on_delete=models.CASCADE,)
    msg = models.CharField(max_length=1024)

    class Meta:
        db_table = '"serviceindex"."logentry"'

# FORMS

class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ('name', 'description', 'hostname', 'failover_process',
                'failover_last_tested', 'service_last_verified', 'dependencies', 'lb', 'ha', 'otp','nagios')
        labels = {'lb': 'Load Balanced', 'ha': 'High Availability',
                'otp': 'OTP Enabled', 'nagios':  'Service checked by Nagios'}
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'description': forms.Textarea(attrs={'class':'form-control', 'rows':'3'}),
            'hostname': forms.TextInput(attrs={'class':'form-control'}),
            'failover_process': forms.Textarea(attrs={'class':'form-control', 'rows':'3'}),
            'failover_last_tested': forms.DateInput(format='%m/%d/%Y', attrs={'class':'form-control', 'placeholder':'mm/dd/yyyy'}),
            'service_last_verified': forms.DateInput(format='%m/%d/%Y', attrs={'class':'form-control', 'placeholder':'mm/dd/yyyy'}),
            'dependencies': forms.Textarea(attrs={'class':'form-control', 'rows':'3'}),
        }

class MetricsForm(forms.Form):
    start_date = forms.DateField(required=False,
            widget=forms.DateInput(format='%m/%d/%Y',
            attrs={'class':'form-control', 'placeholder':'mm/dd/yyyy'}))
    end_date = forms.DateField(required=False,
            widget=forms.DateInput(format='%m/%d/%Y',
            attrs={'class':'form-control', 'placeholder':'mm/dd/yyyy'}))
    
class LinkForm(forms.ModelForm):
# EXCLUDE id and service; service foreign key causes form validation failure
    class Meta:
        model = Link
        fields = '__all__'
        exclude = ('service',)
        widgets = {
            'id': forms.HiddenInput(),
            'url': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class':'form-control', 'rows':'2'}),
        }

class HostForm(forms.ModelForm):
    #TYPE_CHOICES = (
    #    ('primary', 'primary'),
    #    ('secondary', 'secondary'),
    #    ('tertiary', 'tertiary'),
    #    ('prod', 'prod'),
    #    ('test', 'test'),
    #)
    def clean(self):
        """
        For several fields, either an existing entry must be selected from 
        drop-down, or a new entry entered.  This override of clean() checks
        for all of these cases.
        """
        cleaned_data = super(HostForm, self).clean()
        # using .get() will not give you a KeyError if key doesn't exist
        location = cleaned_data.get('location')
        location_new = cleaned_data.get('location_new')
        if not location and not location_new:
            msg = u'Please select existing location or enter name of new one.'
            self._errors['location'] = self.error_class([msg])
            del cleaned_data['location']
            del cleaned_data['location_new']
        # three checks for staff entries
        msg = u'Please select existing staff or enter new name and email.'
        for s in ('sys_admin', 'poc_primary', 'poc_backup'):
            name = cleaned_data.get('_'.join([s, 'name']))
            email = cleaned_data.get('_'.join([s, 'email']))
            phone = cleaned_data.get('_'.join([s, 'phone']))
            if not cleaned_data[s] and (not name or not email):
                self._errors[s] = self.error_class([msg])
                del cleaned_data['_'.join([s,'name'])]
                del cleaned_data['_'.join([s,'email'])]
                del cleaned_data['_'.join([s,'phone'])]
        return cleaned_data

#    def clean_service(self):    # We set this, so we don't affect changed_data
#        return self.cleaned_data['service']
        
    #type = forms.ChoiceField(choices=TYPE_CHOICES,
    #        widget=forms.Select(attrs={'class':'form-control'}))
    # REMOVED empty_label=None on 11/5/2022
    id = forms.HiddenInput()
    location = forms.ModelChoiceField(required=False, label='Location',
            queryset=Site.objects.all().order_by('site'),
            widget=forms.Select(attrs={'class':'form-select'}))
    location_new = forms.CharField(required=False, label='Site',
            widget=forms.TextInput(attrs={'class':'form-control'}))
    label = forms.CharField(
            widget=forms.TextInput(attrs={'class':'form-control'}))
    hostname = forms.CharField(required=False,
            widget=forms.TextInput(attrs={'class':'form-control'}))
    ip_address = forms.CharField(required=False,
            widget=forms.TextInput(attrs={'class':'form-control'}))
    qualys = forms.BooleanField(required=False, label='Qualys',
            widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    nagios  = forms.BooleanField(label='Checked by Nagios', required=False,
            widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    syslog_standard_10514 = forms.BooleanField(label='Syslog default to 10514', required=False,
            widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    syslog_relp_10515 = forms.BooleanField(label='Syslog RELP to 10515', required=False,
            widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    availability = forms.ModelChoiceField(required=False,
            queryset=Availability.objects.all(),
            widget=forms.Select(attrs={'class':'form-select'}))
    support = forms.ModelChoiceField(required=False,
            queryset=Support.objects.all(),
            widget=forms.Select(attrs={'class':'form-select'}))
    sys_admin = forms.ModelChoiceField(required=False, label="Sys Admin",
            queryset=Staff.objects.all().order_by('last_name'),
            widget=forms.Select(attrs={'class':'form-select'}))
    sys_admin_name = forms.CharField(required=False, label="Name",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Name'}))
    # TODO should this not be EmailField ???
    sys_admin_email = forms.CharField(required=False, label="Email",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Email'}))
    sys_admin_phone = forms.CharField(required=False, label="Phone",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Phone'}))
    poc_primary = forms.ModelChoiceField(required=False, label="Primary POC",
            queryset=Staff.objects.all().order_by('last_name'),
            widget=forms.Select(attrs={'class':'form-select'}))
    poc_primary_name = forms.CharField(required=False, label="Name",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Name'}))
    poc_primary_email = forms.CharField(required=False, label="Email",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Email'}))
    poc_primary_phone = forms.CharField(required=False, label="Phone",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Phone'}))
    poc_backup = forms.ModelChoiceField(required=False, label="Backup POC",
            queryset=Staff.objects.all().order_by('last_name'),
            widget=forms.Select(attrs={'class':'form-select'}))
    poc_backup_name = forms.CharField(required=False, label="Name",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Name'}))
    poc_backup_email = forms.CharField(required=False, label="Email",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Email'}))
    poc_backup_phone = forms.CharField(required=False, label="Phone",
            widget=forms.TextInput(attrs={'class':'form-control', 'placeholder':'Phone'}))
    host_last_verified = forms.DateField(required=False, label = 'Host last verified',
            widget=forms.DateInput(attrs={'class':'form-control', 'placeholder':'mm/dd/yyyy'}))
    note = forms.CharField(required=False,
            widget=forms.Textarea(attrs={'class':'form-control', 'rows':'3'}))
    class Meta:
        model = Host
        fields = '__all__'
        exclude = ('service',)

class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField()

class ExportChoicesForm(forms.Form):
    """
    This form is for selecting fields for custom listing of services.
    Everything is a BooleanField checkbox.  Explicitly adding class names to
    widgets to provide 'select all' functionality via jquery in template.
    """
    description = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    dependencies = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    service_hostname = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    failover_process = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    failover_last_tested = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    service_last_verified = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    lb = forms.BooleanField(label='Load Balanced', required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    ha = forms.BooleanField(label='High Availability', required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    otp = forms.BooleanField(label='OTP Enabled', required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))
    nagios_service = forms.BooleanField(label='Service checked by Nagios', required=False,
        widget=forms.CheckboxInput(attrs={'class':'first_row'}))

    location = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    hostname = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    ip_address = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    availability = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    support = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    sys_admin = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    poc_primary = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    poc_backup = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    note = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    host_last_verified = forms.BooleanField(required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    qualys = forms.BooleanField(label='Scanned by Qualys', required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    nagios = forms.BooleanField(label='Checked by Nagios', required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    syslog_standard_10514 = forms.BooleanField(label='Default Syslog to 10514', required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))
    syslog_relp_10515 = forms.BooleanField(label='RELP Syslog to 10515', required=False,
        widget=forms.CheckboxInput(attrs={'class':'second_row'}))

class StaffForm(forms.ModelForm):
    """For editing contact info"""
    class Meta:
        model = Staff
        fields = ('name', 'last_name', 'email', 'phone', 'deleted')
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'last_name': forms.TextInput(attrs={'class':'form-control'}),
            'email': forms.TextInput(attrs={'class':'form-control'}),
            'phone': forms.TextInput(attrs={'class':'form-control'}),
            'deleted': forms.CheckboxInput(attrs={'class':'first_row'}),
        }

class AddEventForm(forms.ModelForm):

    class Meta:
        model = Event
        fields = ('name', 'description')
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'description': forms.Textarea(attrs={'class':'form-control',
                    'rows':'7'}),
        }
class UpdateEventForm(forms.ModelForm):

    class Meta:
        model = HostEventLog
        fields = ('status', 'note')
        widgets = {
            'note': forms.Textarea(attrs={'class':'form-control',
                    'rows':'7'}),
        }
