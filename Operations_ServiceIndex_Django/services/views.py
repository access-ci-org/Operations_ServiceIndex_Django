from django.core.serializers import serialize
from django.shortcuts import render, redirect
from django.forms.formsets import formset_factory
from django.forms import modelformset_factory
from django import http
from django.urls import reverse, reverse_lazy
from django.template.loader import get_template
from django.template import Context
from django.utils import timezone

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings

from services.models import *
from services.serializers import *
import services.signals

import collections
import json
import logging
logger = logging.getLogger(__name__)
import re

def editors_check(user):
    return user.groups.filter(name='editors').exists()

def viewers_check(user):
    return user.groups.filter(name='editors').exists() or user.groups.filter(name='viewers').exists()

def unprivileged(request):
    return render(request, 'services/unprivileged.html')

def is_privileged(request):
    return True if request.user.username == 'navarro' else False

@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def index(request):
    """
    Main index view of list of services; can have one GET parameter specifying
    if all panels should be expanded or collapsed (collapsed by default)
    """
    # clear any locks by current user
    EditLock.objects.filter(username=request.user.username).delete()

    if editors_check(request.user):
        editor = True
    else:
        editor = False
        
    expand_all = 0
    if request.GET:
        options = request.GET.dict()
        if 'expand_all' in options:
            expand_all = int(options['expand_all'])
    services = []
    for s in Service.objects.order_by('name'):
        services.append({'service': s, 'hosts': s.host_set.all(),
                'log': LogEntry.objects.filter(service=s).order_by('-timestamp')})
    
    context = {'page': 'index',
            'services': services,
            'expand_all': expand_all, 'editor':editor,
            'app_name': settings.APP_NAME}
    return render(request, 'services/services_index.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def add_service(request):
    service_form = ServiceForm(prefix='service', instance=Service())

    LinkFormSet = modelformset_factory(Link, form=LinkForm, extra=1)
    link_formset = LinkFormSet(prefix='links', queryset=Link.objects.none())

    HostFormSet = modelformset_factory(Host, form=HostForm, extra=1)
    host_formset = HostFormSet(prefix='hosts', queryset=Host.objects.none())
    
    context = {'page': 'service',
            'form': service_form,
            'link_formset': link_formset,
            'host_formset': host_formset,
            'service_id': 0,
            'debug': 'first time',
            'privileged': is_privileged(request),
            'app_name': settings.APP_NAME}
    return render(request, 'services/service.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def edit_service(request, service_id):
    # TODO check for valid service_id and return message??
    service = Service.objects.get(pk=service_id)
    if service.deprecated:
        return redirect(reverse('services:index'))

    # clear any locks by current user
    EditLock.objects.filter(username=request.user.username).delete()
    locks = EditLock.objects.filter(service=service)
    if locks: # Other locks on this service
        # check timestamps?
        return redirect(reverse('services:edit_sorry'))
    else:
        EditLock.objects.create(service=service, username=request.user.username)

    service_form = ServiceForm(prefix='service', instance=service)

    related_links = service.link_set.all()
    link_extra = 0 if related_links else 1 # An empty entry if there are none
    LinkFormSet = modelformset_factory(Link, form=LinkForm, extra=link_extra, can_delete=True)
    link_formset = LinkFormSet(prefix='links', queryset=related_links)

    related_hosts = service.host_set.all()
    host_extra = 0 if related_hosts else 1 # An empty entry if there are none
    HostFormSet = modelformset_factory(Host, form=HostForm, extra=host_extra, can_delete=True)
    host_formset = HostFormSet(prefix='hosts', queryset=related_hosts)
    
    context = {'page': 'service',
            'form': service_form,
            'host_formset': host_formset,
            'link_formset': link_formset,
            'service_id': service_id,
            'debug': 'edit',
            'privileged': is_privileged(request),
            'app_name': settings.APP_NAME
    }
    return render(request, 'services/service.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def update_service(request):
    """
    Form for editing a service; the hidden service_id is None/zero for a new service
    """
    service_id = int(request.POST['service_id'])
    service = Service.objects.get(pk=service_id) if service_id else Service()
    service_form = ServiceForm(request.POST, prefix='service', instance=service)

    can_delete = True if service_id else False
    
    related_links = service.link_set.all() if service_id else Link.objects.none()
    link_extra = 1 if not service_id or not related_links else 0
    LinkFormSet = modelformset_factory(Link, form=LinkForm, can_delete=can_delete, extra=link_extra)
    link_formset = LinkFormSet(request.POST, prefix='links', queryset=related_links)

    related_hosts = service.host_set.all() if service_id else Host.objects.none()
    host_extra = 1 if not service_id or not related_hosts else 0
    HostFormSet = modelformset_factory(Host, form=HostForm, can_delete=can_delete, extra=host_extra)
    host_formset = HostFormSet(request.POST, prefix='hosts', queryset=related_hosts)

    # Prepare the context to return to the form if there are errors when adding a link or host
    CTX = {'page': 'service',
            'form': service_form,
            'host_formset': host_formset,
            'link_formset': link_formset,
            'service_id': service_id,
            'debug': None,
            'privileged': is_privileged(request),
            'app_name': settings.APP_NAME}
    
    if 'add_link' in request.POST:
        CTX['debug'] = 'add link'
        PCP = request.POST.copy()
        PCP['links-TOTAL_FORMS'] = int(PCP['links-TOTAL_FORMS']) + 1
        CTX['link_formset'] = LinkFormSet(PCP, prefix='links', queryset=related_links)
        return render(request, 'services/service.html', CTX)

    if 'add_host' in request.POST:
        CTX['debug'] = 'add host'
        PCP = request.POST.copy()
        PCP['hosts-TOTAL_FORMS'] = int(PCP['hosts-TOTAL_FORMS']) + 1
        CTX['host_formset'] = HostFormSet(PCP, prefix='hosts', queryset=related_hosts)
        return render(request, 'services/service.html', CTX)

    # Processing a 'Save'
    CTX['debug'] = 'updating'

    if not service_form.is_valid():
        return render(request, 'services/service.html', CTX)

    # if service_id != 0, then we're editing existing service
    if not service_id:
        msg = 'added new'
    elif service_form.has_changed():
        msg = 'updated'
    else:
        msg = None
    if msg:
        service = service_form.save()
        logger.info('{} {} \'{}\' service'.format(request.user.username, msg, service.name))
        make_log_entry(request.user.username, msg, service=service)
    
    ERRORS = 0
    # save any valid links and add to service
    for link_form in link_formset:
        link_form.instance.service_id = service.id
        if link_form.has_changed():
            if not link_form.is_valid():
                return render(request, 'services/service.html', CTX)
            link_form.save()
    link_formset.save()

    # save any valid hosts and add to service
    ADDED = []
    UPDATED = []
    for host_form in host_formset:
        host_form.instance.service_id = service.id
        if host_form.has_changed():
            if not host_form.is_valid():
                return render(request, 'services/service.html', CTX)

            if not host_form.cleaned_data['location']:
                host_form.instance.location, created = Site.objects.get_or_create(
                        site=host_form.cleaned_data['location_new'])

            if not host_form.cleaned_data['sys_admin']: # Have new person
                last, first = re.split(r'\W+', host_form.cleaned_data['sys_admin_name'], maxsplit=1)
                host_form.instance.sys_admin, created = Staff.objects.get_or_create(
                        last_name=last,
                        name=first,
                        email=host_form.cleaned_data['sys_admin_email'],
                        phone=host_form.cleaned_data['sys_admin_phone'])
                if created:
                    msg = 'added new'
                    logger.info('{} {} \'{}\' staff'.format(request.user.username, msg, host_form.instance.sys_admin))
                    make_log_entry(request.user.username, msg, staff=host_form.instance.sys_admin)

            if not host_form.cleaned_data['poc_primary']: # Have new person
                last, first = re.split(r'\W+', host_form.cleaned_data['poc_primary_name'], maxsplit=1)
                host_form.instance.poc_primary, created = Staff.objects.get_or_create(
                        last_name=last,
                        name=first,
                        email=host_form.cleaned_data['poc_primary_email'],
                        phone=host_form.cleaned_data['poc_primary_phone'])
                if created:
                    msg = 'added new'
                    logger.info('{} {} \'{}\' staff'.format(request.user.username, msg, host_form.instance.poc_primary))
                    make_log_entry(request.user.username, msg, staff=host_form.instance.poc_primary)

            if not host_form.cleaned_data['poc_backup']: # Have new person
                last, first = re.split(r'\W+', host_form.cleaned_data['poc_backup_name'], maxsplit=1)
                last_name, first_name = host_form.cleaned_data['poc_backup_name'].split(None, 1)
                host_form.instance.poc_backup, created = Staff.objects.get_or_create(
                        last_name=last,
                        name=first,
                        email=host_form.cleaned_data['poc_backup_email'],
                        phone=host_form.cleaned_data['poc_backup_phone'])
                if created:
                    msg = 'added new'
                    logger.info('{} {} \'{}\' staff'.format(request.user.username, msg, host_form.instance.poc_backup))
                    make_log_entry(request.user.username, msg, staff=host_form.instance.poc_backup)
            msg = 'updated' if host_form.instance.id else 'added new'
            host_form.save()
            logger.info('{} {} \'{}\' service \'{}\' host'.format(request.user.username, msg, service.name, host_form.instance.label))
            make_log_entry(request.user.username, msg, service=service, host=host_form.instance)
    host_formset.save()
        
    if 'deprecated' in request.POST:
        service.deprecated = True
        service.save()
        msg = 'deprecated'
        logger.info('{} {} \'{}\' service'.format(request.user.username, msg, service.name))
        make_log_entry(request.user.username, msg, service=service)
        
    if link_formset.total_error_count() == 0 and host_formset.total_error_count() == 0:
        return redirect(reverse('services:index'))

    return render(request, 'services/service.html', CTX)


@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def export(request):
    """
    Shows form for selecting fields; when fields are selected, renders plain
    text listing.
    """
    possible_service_fields = ['description', 'dependencies', 'service_hostname',
            'failover_process', 'failover_last_tested', 'service_last_verified', 'lb', 'ha', 'otp','nagios_service']
    possible_host_fields = ['location', 'hostname', 'ip_address',
            'availability', 'support', 'sys_admin', 'host_last_verified',
            'poc_primary', 'poc_backup', 'note','qualys', 'nagios', 'syslog_standard_10514', 'syslog_relp_10515']
    if request.POST:
        form = ExportChoicesForm(request.POST)
        if form.is_valid():
            # populate lists based on what fields were chosen
            service_fields = []
            for field in possible_service_fields:
                if form.cleaned_data[field]:
                    service_fields.append(field)
            host_fields = []
            for field in possible_host_fields:
                if form.cleaned_data[field]:
                    host_fields.append(field)
            # make listing
            services = []
            # TODO need quotes around some fields ??
            for s in Service.objects.order_by('name'):
                service = {'fields':[s.name,], 'hosts':[]}
                for field in service_fields:
                    # special case for service hostname and nagios since its form name is
                    # different than its model name
                    if field == 'service_hostname':
                        service['fields'].append(getattr(s, 'hostname'))
                    elif field == 'nagios_service':
                        service['fields'].append(getattr(s,'nagios'))
                    else:
                        service['fields'].append(getattr(s, field))
                if host_fields:
                    for h in s.host_set.all():   # order_by ??
                        host = [h.label,]
                        for field in host_fields:
                            # use str() here because some are objects
                            host.append(str(getattr(h, field)))
                        service['hosts'].append(host)
                services.append(service)
            # render plain text listing
            response = http.HttpResponse(content_type='text/plain')
            t = get_template('services/export.txt')
            context = {'services':services}
            response.write(t.render(context, request))
            msg = '{} exported data'.format(request.user.username)
            logger.info(msg)
            return response
    else:
        form = ExportChoicesForm()

    # separate out fields for template form
    service_fields = []
    host_fields = []
    # iterating over a form in this manner gives you BoundField objects
    # (if you use form.fields['name'], you don't get BoundField objects)
    for field in form:
        if field.name in possible_service_fields:
            service_fields.append(field)
        else:
            host_fields.append(field)
    context = {'page': 'export', 'service_fields': service_fields,
            'host_fields': host_fields, 'app_name': settings.APP_NAME}
    return render(request, 'services/export_choices.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def custom(request):
    """
    Shows form for selecting fields; when fields are selected, renders 
    html table (with print option?)
    """

    possible_service_fields = ['description', 'dependencies', 'service_hostname',
            'failover_process', 'failover_last_tested', 'service_last_verified', 'lb', 'ha', 'otp']
    possible_host_fields = ['location', 'hostname', 'ip_address',
            'availability', 'support', 'sys_admin', 'host_last_verified',
            'poc_primary', 'poc_backup', 'note']
    if request.POST:
        form = ExportChoicesForm(request.POST)
        if form.is_valid():
            # populate lists based on what fields were chosen
            fields = []
            headings = ['service',]
            for field in possible_service_fields:
                if form.cleaned_data[field]:
                    fields.append(field)
                    headings.append(field)
            #host_fields = []
            #for field in possible_host_fields:
            #    if form.cleaned_data[field]:
            #        host_fields.append(field)

            # make listing
            rows = []
            # TODO need quotes around some fields ??
            for s in Service.objects.order_by('name'):
                row = [s.name,]
                for field in fields:
                    # special case for service hostname since its form name is
                    # different than its model name
                    if field == 'service_hostname':
                        row.append(getattr(s, 'hostname'))
                    else:
                        row.append(getattr(s, field))
                #if host_fields:
                #    for h in s.host_set.all():   # order_by ??
                #        host = [h.label,]
                #        for field in host_fields:
                #            # use str() here because some are objects
                #            host.append(str(getattr(h, field)))
                #        service['hosts'].append(host)
                rows.append(row)
            # render plain text listing
            context = {'headings':headings, 'rows':rows,}
            return render(request, 'services/custom.html', context)
            #response = http.HttpResponse(content_type='text/plain')
            #t = get_template('services/export.txt')
            #context = Context({'services':services})
            #response.write(t.render(context))
            #return response

    else:
        form = ExportChoicesForm()

    # separate out fields for template form
    service_fields = []
    host_fields = []
    # iterating over a form in this manner gives you BoundField objects
    # (if you use form.fields['name'], you don't get BoundField objects)
    for field in form:
        if field.name in possible_service_fields:
            service_fields.append(field)
        else:
            host_fields.append(field)
    context = {'service_fields':service_fields,
            'host_fields':host_fields}
    return render(request, 'services/export_choices.html', context)

@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def hosts(request, order_field='hostname'):
#    hosts = {}
    hosts = collections.OrderedDict()
    hostnames = []
    hosts_list = Host.objects.order_by(order_field)
    # TODO this should not get ones that are deprecated

    if order_field != 'service__name':
        for h in hosts_list: 
            if h.hostname in hostnames:
                if hosts[h.hostname]['service'] is not None and len(hosts[h.hostname]['service']) > 0:
                    services = hosts[h.hostname]['service']
                else:
                    services = []
                services.append({'name':h.service.name, 'deprecated':h.service.deprecated})
                hosts[h.hostname]['label']= hosts[h.hostname]['label'] + " | "+h.label
                hosts[h.hostname]['service'] = services
            else:
                services = []
                services.append({'name':h.service.name,'deprecated':h.service.deprecated })
                hosts[h.hostname] = {'hostname': h.hostname,
                    'ip': h.ip_address,
                    'site': h.location.site,
                    'label': h.label,
                    'service': services,
                    'deprecated': h.service.deprecated,
                    'qualys': h.qualys,
                    'nagios': h.nagios,
                    'syslog_standard_10514': h.syslog_standard_10514,
                    'syslog_relp_10515': h.syslog_relp_10515
                    }
                hostnames.append(h.hostname)    
    else:
        for h in hosts_list:
            if hosts is not None and h.hostname in hosts and hosts[h.hostname]['service'] is not None and len(hosts[h.hostname]['service']) > 0:
                services = hosts[h.hostname]['service']
                hostlabel = hosts[h.hostname]['label'] + " | "+h.label
            else:
                services = []
                hostlabel = h.label
            services.append({'name':h.service.name,'deprecated':h.service.deprecated})
            hosts[h.hostname] = {'hostname': h.hostname, 'ip': h.ip_address,
                'site': h.location.site,
                'label': hostlabel, 'service': services,
                'deprecated': h.service.deprecated, 'qualys': h.qualys, 'nagios': h.nagios,
                'syslog_standard_10514': h.syslog_standard_10514, 'syslog_relp_10515': h.syslog_relp_10515}
    context = {'page': 'hosts', 'hosts': hosts,
            'order_field': order_field,
            'app_name': settings.APP_NAME}
    return render(request, 'services/hosts.html', context)

@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def hosts_by_service(request):
    s = ''
    services = []
    index = -1
    for i in Host.objects.order_by('service__name'):
        h = {'host':i.hostname, 'ip':i.ip_address, 'site': i.location.site}
        if i.service.name == s:
            services[index]['hosts'].append(h)
        else:
            services.append({'service':i.service.name, 'hosts':[h,]})
            index += 1
            s = i.service.name

    context = {'services':services,}
    return render(request, 'services/hosts_by_service.html', context)

@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def people(request):
    people = []
    # TODO this should not get ones that are deprecated
    for p in Staff.objects.filter(deleted=False).order_by('last_name'):
        poc_primary_hosts = p.poc_primary_instance_set.all()
        poc_backup_hosts = p.poc_backup_instance_set.all()
        sys_admin_hosts = p.sys_admin_instance_set.all()
        people.append({'last_name':p.last_name, 'name':p.name, 'email':p.email, 'id':p.id,
                'phone':p.phone,
                'poc_primary_hosts':poc_primary_hosts,
                'poc_backup_hosts':poc_backup_hosts,
                'sys_admin_hosts':sys_admin_hosts})
    #            'label':h.label, 'service':h.service.name,
    #            'deprecated':h.service.deprecated})
    context = {'page': 'people', 'people': people,
            'app_name': settings.APP_NAME}
    return render(request, 'services/people.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def edit_staff(request, staff_id):
    staff = Staff.objects.get(pk=staff_id)
    if request.POST:
        form = StaffForm(request.POST, instance=staff)
        if form.is_valid():
            if form.has_changed():
                staff.email = form.cleaned_data['email']
                staff.phone = form.cleaned_data['phone']
                staff.save()
                msg = 'updated'
                logger.info('{} {} \'{}\' staff'.format(request.user.username, msg, staff.name))
                make_log_entry(request.user.username, msg, staff=staff)
            return redirect(reverse('services:people'))
    else:
        form = StaffForm(initial={'name':staff.name, 'last_name':staff.last_name, 'email':staff.email, 'phone':staff.phone})

    context = {'page': 'people', 'form':form, 
            'staff_name':staff.name, 'staff_id':staff_id,
            'app_name': settings.APP_NAME}
    return render(request, 'services/edit_staff.html', context)


@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def metrics(request):
    start = None
    end = None
    if request.POST:
        form = MetricsForm(request.POST)
        if form.is_valid():
            if form.cleaned_data['start_date']:
                start = datetime.combine(form.cleaned_data['start_date'], time.min, tzinfo=ZoneInfo("US/Central"))
            if form.cleaned_data['end_date']:
                end = datetime.combine(form.cleaned_data['end_date'], time.max, tzinfo=ZoneInfo("US/Central"))
    else:
        end = timezone.now()
        week = timedelta(days=7)
        start = end - week
        form = MetricsForm(initial={'start_date':start, 'end_date':end})

    # count logs
    if start and end:
        logs = LogEntry.objects.filter(timestamp__gte=start, timestamp__lte=end, service__isnull=False)
        heading = ('Activity from ' + start.strftime('%m/%d/%Y') + ' to ' +
                end.strftime('%m/%d/%Y'))
    elif start:
        logs = LogEntry.objects.filter(timestamp__gte=start, service__isnull=False)
        heading = 'Activity since ' + start.strftime('%m/%d/%Y') 
    elif end:
        logs = LogEntry.objects.filter(timestamp__lte=end, service__isnull=False)
        heading = 'Activity before ' + end.strftime('%m/%d/%Y') 
    else:
        logs = LogEntry.objects.filter(service__isnull=False)
        heading = 'All Activity'

    updates = 0
    new_services = 0
    new_hosts = 0
    deprecations = 0
    for le in logs:
        if 'updated' in le.msg:
            updates += 1
        elif 'added new' in le.msg:
            if 'new link' in le.msg:
                updates += 1
            elif 'host to' in le.msg:
                new_hosts += 1
            else:
                new_services += 1
        elif 'deprecated' in le.msg:
            deprecations += 1

    # get current totals
    total_services = Service.objects.filter(deprecated=False).count()
    total_hosts = Host.objects.filter(service__deprecated=False).count()

    context = {'page': 'metrics', 'form':form, 'heading':heading,
            'updates':updates, 'new_services':new_services, 
            'new_hosts':new_hosts, 'deprecations':deprecations,
            'total_services':total_services, 'total_hosts':total_hosts,
            'app_name': settings.APP_NAME}
    return render(request, 'services/metrics.html', context)


@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def listing(request):
    """
    This is used for text dump of all services with fields separated by pipes;
    produces txt file that can be easily parsed to re-populate database;
    technique for rendering txt file is documented here:
    https://docs.djangoproject.com/en/dev/howto/outputting-csv/
    """
    debug = request.user.username
    #debug = request.session['debug']
    response = http.HttpResponse(content_type='text/plain')
    services = []
    for s in Service.objects.order_by('name'):
        services.append({'service': s, 'hosts': s.host_set.all()})
    
    t = get_template('services/listing.txt')
    #context = Context({'services':services})
    context = Context({'services':services, 'debug':debug})
    response.write(t.render(context))
    return response

@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def log_listing(request):
    """
    This is used for text dump of all log entries;
    produces txt file that can be easily parsed to re-populate database;
    technique for rendering txt file is documented here:
    https://docs.djangoproject.com/en/dev/howto/outputting-csv/
    """
    response = http.HttpResponse(content_type='text/plain')
    logs = LogEntry.objects.all().order_by('timestamp')
    
    t = get_template('services/log_listing.txt')
    context = Context({'logs':logs})
    response.write(t.render(context))
    return response

def make_log_entry(username, msg, service=None, host=None, staff=None, event=None):
    """
    Saves service, host, staff, and event changes to a table so that we can display the history
    We also use logger to generate normal/critical log file entries that can be aggregated with rsyslog
    """
    le = LogEntry(username=username, msg=msg, service=service, host=host, staff=staff, event=event)
    le.save()

@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def view_log(request):
    log = LogEntry.objects.all().order_by('-timestamp')
    context = {'page': 'view_log', 'log': log, 'app_name': settings.APP_NAME}
    return render(request, 'services/view_log.html', context)

@login_required
def login(request):
    remote_ip = request.META.get('HTTP_X_FORWARDED_FOR')
    if not remote_ip:
        remote_ip = request.META.get('REMOTE_ADDR')
    msg = 'login from {}'.format(remote_ip)
#   Standard logging handled in signals.py
#    logger.info('{} {}'.format(request.user.username, msg))
    make_log_entry(request.user.username, msg)
    return redirect(reverse('services:index'))

@login_required
def clear_and_logout(request):
#   Clear any locks by current user
    EditLock.objects.filter(username=request.user.username).delete()
#   Standard logging handled in signals.py
    return redirect(reverse('account_logout'))

@login_required
def edit_sorry(request):
    context = {'app_name': settings.APP_NAME}
    return render(request, 'services/edit_sorry.html', context)

@login_required
@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def events(request):
    events = []
    for e in Event.objects.order_by('-created'):
        num_hosts = HostEventStatus.objects.filter(event=e).count()
        unchecked = HostEventStatus.objects.filter(event=e,
                status=HostEventStatus.UNCHECKED).count()
        in_progress = HostEventStatus.objects.filter(event=e,
                status=HostEventStatus.IN_PROGRESS).count()
        compliant = HostEventStatus.objects.filter(event=e,
                status=HostEventStatus.COMPLIANT).count()
        na = HostEventStatus.objects.filter(event=e,
                status=HostEventStatus.NA).count()
        events.append({'created': e.created, 'name': e.name, 'id': e.id,
                'description': e.description,
                'totals':{
                    'hosts': num_hosts,
                    'unchecked': unchecked,
                    'in_progress': in_progress,
                    'compliant': compliant,
                    'na': na
                    }
                #'unchecked':float(unchecked)/float(num_hosts)*100.0,}
                })

    context = {'page': 'events', 'events':events,
            'app_name': settings.APP_NAME}
    return render(request, 'services/events.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def add_event(request):
    if request.POST:
        form = AddEventForm(request.POST)
        if form.is_valid():
            e = form.save()     # creates Event
            # make status entries for each host
            for h in Host.objects.filter(service__deprecated=False):
                hes = HostEventStatus(event=e, host=h, status=HostEventStatus.UNCHECKED)
                hes.save()
            msg = 'added new'
            logger.info('{} {} \'{}\' event'.format(request.user.username, msg, e.name))
            make_log_entry(request.user.username, msg, event=e)
            return redirect(reverse('services:events'))
    else:
        form = AddEventForm()

    context = {'page': 'events', 'form':form, 
            'app_name': settings.APP_NAME}
    return render(request, 'services/add_event.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def event(request, event_id):
    # col offsets to use in template for each status tag
    cols = {HostEventStatus.UNCHECKED:0,HostEventStatus.IN_PROGRESS:3,
            HostEventStatus.COMPLIANT:6,HostEventStatus.NA:9}
    # label-types to use in template for each status tag
    label_types = {HostEventStatus.UNCHECKED:'danger',
            HostEventStatus.IN_PROGRESS:'warning',
            HostEventStatus.COMPLIANT:'success',
            HostEventStatus.NA:'primary'}
    event = Event.objects.get(pk=event_id)
    hosts = []
    for hes in HostEventStatus.objects.filter(event=event).order_by(
            'host__hostname'):
        hosts.append({'hes_id':hes.id, 
                'hostname':hes.host.hostname,'ip':hes.host.ip_address,
                'logs':HostEventLog.objects.filter(event=hes.event,
                host=hes.host).order_by('timestamp'),
                'status':hes.status,'col':cols[hes.status],
                'label_type':label_types[hes.status]})
    context = {'page': 'events', 'event':event, 'hosts':hosts,
            'app_name': settings.APP_NAME}
    return render(request, 'services/event.html', context)

@login_required
@user_passes_test(editors_check, login_url=reverse_lazy('services:unprivileged'))
def update_event(request, hes_id):
    hes = HostEventStatus.objects.get(pk=hes_id)

    if request.POST:
        form = UpdateEventForm(request.POST)
        if form.is_valid():
            log = HostEventLog(event=hes.event,host=hes.host,
                    username=request.user.username,
                    status=form.cleaned_data['status'],
                    note=form.cleaned_data['note'])
            log.save()
            hes.status = form.cleaned_data['status']
            hes.save()
            msg = '{} logged event for \'{}\' host'.format(request.user.username, hes.host.hostname)
            logger.info(msg)
            return redirect(reverse('services:event', args=[hes.event.id]))
    else:
        #form = UpdateEventForm(instance=hes)
        form = UpdateEventForm(initial={'status':hes.status})

    context = {'page': 'events', 'form':form, 'hes':hes,
            'app_name': settings.APP_NAME}
    return render(request, 'services/update_event.html', context)


# the remainder are tests that are no longer being used
def do_pdf(template_src, context_dict):
    """
    Got this example from:
    http://20seven.org/journal/2008/11/11/pdf-generation-with-pisa-in-django/
    It uses pisa which is part of xhtml2pdf
    """
    template = get_template(template_src)
    context = Context(context_dict)
    html = template.render(context)
    result = StringIO.StringIO()
    pdf = pisa.pisaDocument(StringIO.StringIO(
            html.encode("UTF-8")), result)
    if not pdf.err:
        return http.HttpResponse(result.getvalue(), mimetype='application/pdf')
    return http.HttpResponse('pdf error! %s' % cgi.escape(html))

@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def make_pdf(request):
    services = []
    for s in Service.objects.order_by('name'):
        services.append({'service': s, 'instances': s.instance_set.all()})
    
    context = {'services':services}
    return do_pdf('services/services_for_pdf.html', context)

@user_passes_test(viewers_check, login_url=reverse_lazy('services:unprivileged'))
def api_hosts(request):
    objects = Host.objects.all()
    serializer = Host_Serializer(objects, many=True)
    response_obj = {
        'status_code': '200',
        'results': serializer.data
    }
    return http.JsonResponse(response_obj)
