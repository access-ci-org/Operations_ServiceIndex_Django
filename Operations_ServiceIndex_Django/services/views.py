from django.shortcuts import render, redirect
from django.forms.formsets import formset_factory

from django import http
from django.urls import reverse, reverse_lazy
from django.template.loader import get_template
from django.template import Context
from django.utils import timezone
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings

import logging
logger = logging.getLogger(__name__)
import collections
from services.models import *
import services.signals

def editors_check(user):
    return user.groups.filter(name='editors').exists()

def unprivileged(request):
    return render(request, 'services/unprivileged.html')
            
@login_required
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
def export(request):
    """
    Shows form for selecting fields; when fields are selected, renders plain
    text listing.
    """

    possible_service_fields = ['description', 'dependencies', 
            'service_hostname',
            'failover_process', 'failover_last_tested', 'service_last_verified', 'lb', 'ha', 'otp','nagios_service']
    possible_host_fields = ['location', 'hostname', 'ip_address',
            'availability', 'support', 'sys_admin', 'host_last_verified',
            'poc_primary', 'poc_backup', 'note', 'nagios','qualys']
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
            context = Context({'services':services})
            response.write(t.render(context))
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
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
def custom(request):
    """
    Shows form for selecting fields; when fields are selected, renders 
    html table (with print option?)
    """

    possible_service_fields = ['description', 'dependencies', 
            'service_hostname',
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
            context = {'headings':headings,'rows':rows,}
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
                'log': LogEntry.objects.filter(service=s).order_by(
                '-timestamp')})
    
    context = {'page': 'services', 'services': services, 
            'expand_all': expand_all, 'editor':editor,
            'app_name': settings.APP_NAME}
    return render(request, 'services/index_bootstrap.html', context)

@login_required
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
                hosts[h.hostname] = {'hostname':h.hostname,
                    'ip':h.ip_address,
                    'site': h.location.site,
                    'label':h.label,
                    'service':services,
                    'deprecated':h.service.deprecated,
                    'qualys': h.qualys,
                    'nagios': h.nagios}
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
            hosts[h.hostname] = {'hostname':h.hostname, 'ip':h.ip_address,
                'site': h.location.site,
                'label':hostlabel, 'service':services,
                'deprecated':h.service.deprecated, 'qualys':h.qualys, 'nagios': h.nagios}
    context = {'page': 'hosts', 'hosts': hosts,
            'order_field': order_field,
            'app_name': settings.APP_NAME}
    return render(request, 'services/hosts.html', context)

@login_required
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
def edit_staff(request, staff_id):
    staff = Staff.objects.get(pk=staff_id)
    if request.POST:
        form = StaffForm(request.POST)
        if form.is_valid():
            staff.email = form.cleaned_data['email']
            staff.phone = form.cleaned_data['phone']
            staff.save()
            msg = ''.join([request.user.username,' updated staff \'',
                    staff.name])
            logger.info(msg)
            return redirect(reverse('services:people'))
    else:
        form = StaffForm(initial={'name':staff.name, 'last_name':staff.last_name, 'email':staff.email,'phone':staff.phone})

    context = {'page': 'people', 'form':form, 
            'staff_name':staff.name,
            'staff_id':staff_id,
            'app_name': settings.APP_NAME}
    return render(request, 'services/edit_staff.html', context)


@login_required
def metrics(request):
    start = None
    end = None
    if request.POST:
        form = MetricsForm(request.POST)
        if form.is_valid():
            if form.cleaned_data['start_date']:
                start = form.cleaned_data['start_date']
            if form.cleaned_data['end_date']:
                end = form.cleaned_data['end_date']
    else:
        end = timezone.now()
        week = timedelta(days=7)
        start = end - week
        form = MetricsForm(initial={'start_date':start, 'end_date':end})

    # count logs
    if start and end:
        logs = LogEntry.objects.filter(timestamp__gte=start, timestamp__lte=end)
        heading = ('Activity from ' + start.strftime('%m/%d/%Y') + ' to ' +
                end.strftime('%m/%d/%Y'))
    elif start:
        logs = LogEntry.objects.filter(timestamp__gte=start)
        heading = 'Activity since ' + start.strftime('%m/%d/%Y') 
    elif end:
        logs = LogEntry.objects.filter(timestamp__lte=end)
        heading = 'Activity before ' + end.strftime('%m/%d/%Y') 
    else:
        logs = LogEntry.objects.all()
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

    context = {'page':'metrics', 'form':form, 'heading':heading,
            'updates':updates, 'new_services':new_services, 
            'new_hosts':new_hosts, 'deprecations':deprecations,
            'total_services':total_services, 'total_hosts':total_hosts,
            'app_name': settings.APP_NAME}
    return render(request, 'services/metrics.html', context)


@login_required
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
def listing(request):
    """
    This is used for text dump of all services with fields separated by pipes;
    produces txt file that can be easily parsed to re-populate database;
    technique for rendering txt file is documented here:
    https://docs.djangoproject.com/en/dev/howto/outputting-csv/
    """
    #debug = request.user.is_active
    #if request.user.is_authenticated():
    #    debug = 'YES'
    #else:
    #    debug = 'NO'
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
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
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

def make_log_entry(username,service,msg):
    le = LogEntry(username=username,service=service,msg=msg)
    le.save()

@login_required
def view_log(request):
    log = LogEntry.objects.all().order_by('-timestamp')
    context = {'page': 'view_log', 'log': log,
            'app_name': settings.APP_NAME}
    return render(request, 'services/view_log.html', context)

@login_required
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
def add(request):
    """
    Shows form for adding new entry or editing existing one. Service id is
    hidden field--if it's 0, then we're adding new entry.
    """
    LinkFormSet = formset_factory(LinkForm)
    HostFormSet = formset_factory(HostForm)
    if request.POST:
        service_id = int(request.POST['service_id'])
        num = int(request.POST['host-TOTAL_FORMS'])
        if 'add_host' in request.POST:
            # can't directly alter POST data; must make copy to change
            cp = request.POST.copy()
            # check existing host data
            host_formset = HostFormSet(request.POST, prefix='host')
            # only add host form if previous one is valid
            if host_formset.is_valid():
                cp['host-TOTAL_FORMS'] = int(cp['host-TOTAL_FORMS']) + 1
            host_formset = HostFormSet(cp, prefix='host')

            # keep any existing form fields without doing validation by setting
            #  'initial' values from cp
            form = ServiceForm(initial=cp.dict())
            # have to transform POST fields into initial data fields for formset
            init_data = []
            tmp = LinkForm()
            num = int(cp['link-TOTAL_FORMS'])
            for i in range(0,num):
                prefix = ''.join(['link-', str(i), '-'])
                d = {}
                empty = True
                for field in tmp.fields.keys():
                    d[field] = cp[''.join([prefix, field])]
                    if d[field] != '':
                        empty = False
                if not empty:
                    init_data.append(d)

            if len(init_data) == 0:
                LinkFormSet.extra = 1
                link_formset = LinkFormSet(prefix='link')
            else:
                # initial data will determine how many forms in formset; need to
                #  set 'extra' to 0 so no additional forms will show up
                LinkFormSet.extra = 0
                link_formset = LinkFormSet(initial=init_data, prefix='link')
            debug = 'add host'

        elif 'add_link' in request.POST:
            cp = request.POST.copy()
            link_formset = LinkFormSet(request.POST, prefix='link')
            if link_formset.is_valid():
                cp['link-TOTAL_FORMS'] = int(cp['link-TOTAL_FORMS']) + 1
            link_formset = LinkFormSet(cp, prefix='link')
            form = ServiceForm(initial=cp.dict())
            init_data = []
            tmp = HostForm()
            num = int(cp['host-TOTAL_FORMS'])
            for i in range(0,num):
                prefix = ''.join(['host-', str(i), '-'])
                d = {}
                for field in tmp.fields.keys():
                    d[field] = cp[''.join([prefix, field])]
                init_data.append(d)
            HostFormSet.extra = 0
            host_formset = HostFormSet(initial=init_data, prefix='host')
            debug = 'add link'

        else:
            form = ServiceForm(request.POST)
            host_formset = HostFormSet(request.POST, prefix='host')
            link_formset = LinkFormSet(request.POST, prefix='link')
            debug = 'not valid'
            if (form.is_valid() and host_formset.is_valid() and
                    link_formset.is_valid()):
                # if service_id != 0, then we're editing existing service
                if service_id:
                    service = Service.objects.get(pk=service_id)
                    # set fields to whatever is in form using setattr()
                    for field in form.fields.keys():
                        setattr(service, field, form.cleaned_data[field])
                    service.save()
                    msg = ''.join([request.user.username,' updated \'',
                            service.name,'\' service'])
                    logger.info(msg)
                    make_log_entry(request.user.username,service,msg)
                else:
                    service = form.save()
                    msg = ''.join([request.user.username,' added new \'',
                            service.name,'\' service'])
                    logger.info(msg)
                    make_log_entry(request.user.username,service,msg)

                hosts = service.host_set.all()
                num_hosts = len(hosts)
                links = service.link_set.all()
                num_links = len(links)
                # clean() method of host form checks for required fields; 
                # for several fields, there will either be a model instance 
                # selected or we need to create a new entry;
                # for creating new ones, use get_or_create which will prevent
                # making duplicate of one already in db

                # loop through all host forms in formset; for each, check
                # if we need to create new Site or Staff objects
                index = 0
                for hform in host_formset:
                    if not hform.cleaned_data['location_choice']:
                        location, created = Site.objects.get_or_create(
                                site=hform.cleaned_data['location_site'])
                    else:
                        location = hform.cleaned_data['location_choice']

                    if not hform.cleaned_data['sys_admin_choice']:
                        sys_admin, created = Staff.objects.get_or_create(
                                name=hform.cleaned_data['sys_admin_name'],
                                email=hform.cleaned_data['sys_admin_email'],
                                phone=hform.cleaned_data['sys_admin_phone'])
                        # if created, need to parse for last_name
                        if created:
                            parts = sys_admin.name.rsplit(None,1)
                            if len(parts) == 1:
                                last = parts[0]
                            else:
                                last = parts[1]
                                if (last == 'Jr' or last == 'Jr.' or
                                        last == 'Sr' or last == 'Sr.'):
                                    last = parts[0].rsplit(None,1)[1]
                            sys_admin.last_name = last
                            sys_admin.save()
                    else:
                        sys_admin = hform.cleaned_data['sys_admin_choice']

                    if not hform.cleaned_data['poc_primary_choice']:
                        poc_primary, created = Staff.objects.get_or_create(
                                name=hform.cleaned_data['poc_primary_name'],
                                email=hform.cleaned_data['poc_primary_email'],
                                phone=hform.cleaned_data['poc_primary_phone'])
                        # if created, need to parse for last_name
                        if created:
                            parts = poc_primary.name.rsplit(None,1)
                            if len(parts) == 1:
                                last = parts[0]
                            else:
                                last = parts[1]
                                if (last == 'Jr' or last == 'Jr.' or
                                        last == 'Sr' or last == 'Sr.'):
                                    last = parts[0].rsplit(None,1)[1]
                            poc_primary.last_name = last
                            poc_primary.save()
                    else:
                        poc_primary = hform.cleaned_data['poc_primary_choice']

                    if not hform.cleaned_data['poc_backup_choice']:
                        poc_backup, created = Staff.objects.get_or_create(
                                name=hform.cleaned_data['poc_backup_name'],
                                email=hform.cleaned_data['poc_backup_email'],
                                phone=hform.cleaned_data['poc_backup_phone'])
                        # if created, need to parse for last_name
                        if created:
                            parts = poc_backup.name.rsplit(None,1)
                            if len(parts) == 1:
                                last = parts[0]
                            else:
                                last = parts[1]
                                if (last == 'Jr' or last == 'Jr.' or
                                        last == 'Sr' or last == 'Sr.'):
                                    last = parts[0].rsplit(None,1)[1]
                            poc_backup.last_name = last
                            poc_backup.save()
                    else:
                        poc_backup = hform.cleaned_data['poc_backup_choice']

                    # now create host
                    #TODO if editing, check for existing instances and update
                    if index < num_hosts:
                        hosts[index].location = location
                        hosts[index].hostname = hform.cleaned_data['hostname']
                        hosts[index].ip_address = hform.cleaned_data[
                                'ip_address']
                        hosts[index].label = hform.cleaned_data['label']
                        hosts[index].availability = hform.cleaned_data[
                                'availability']
                        hosts[index].support = hform.cleaned_data['support']
                        hosts[index].sys_admin = sys_admin
                        hosts[index].poc_primary = poc_primary
                        hosts[index].poc_backup = poc_backup
                        hosts[index].note = hform.cleaned_data['note']
                        hosts[index].qualys= hform.cleaned_data['qualys']
                        hosts[index].nagios= hform.cleaned_data['nagios']
                        hosts[index].host_last_verified= hform.cleaned_data['host_last_verified']
                        # TODO log edit of instance
                        #msg = ''.join([request.user.username,' updated \'',
                        #        instances[index].type,'\' instance of \'',
                        #        service.name,'\' service'])
                        #logger.info(msg)
                        #make_log_entry(request.user.username,service,msg)
                        hosts[index].save()
                        
                    else:
                        h = Host(service=service, location=location,
                            hostname=hform.cleaned_data['hostname'],
                            ip_address=hform.cleaned_data['ip_address'],
                            label=hform.cleaned_data['label'],
                            qualys=hform.cleaned_data['qualys'],
                            nagios=hform.cleaned_data['nagios'],
                            availability=hform.cleaned_data['availability'],
                            support=hform.cleaned_data['support'],
                            sys_admin=sys_admin, poc_primary=poc_primary,
                            poc_backup=poc_backup,
                            host_last_verified=hform.cleaned_data['host_last_verified'],
                            note=hform.cleaned_data['note'])
                        h.save()
                        msg = ''.join([request.user.username,' added new \'',
                                h.label,'\' host to \'',
                                service.name,'\' service'])
                        logger.info(msg)
                        make_log_entry(request.user.username,service,msg)
                    index += 1

                # save any valid links and add to service
                index = 0
                for lform in link_formset:
                    #TODO if editing, check for existing links and update
                    if lform.cleaned_data:
                        if index < num_links:
                            links[index].url = lform.cleaned_data['url']
                            links[index].description = lform.cleaned_data['description']
                            # TODO log edit to link
                            #msg = ''.join([request.user.username,
                            #        ' updated link for \'',
                            #        service.name,'\' service'])
                            #logger.info(msg)
                            #make_log_entry(request.user.username,service,msg)
                            links[index].save()
                        else:
                            link = lform.save(commit=False)
                            service.link_set.add(link)
                            msg = ''.join([request.user.username,
                                    ' added new link for \'',
                                    service.name,'\' service'])
                            logger.info(msg)
                            make_log_entry(request.user.username,service,msg)
                    index += 1
                # clear any locks on this service
                # (not needed here since it will be done at top of index view)
                #EditLock.objects.filter(service=service).delete()

                # check for deprecated
                if 'deprecated' in request.POST:
                    service.deprecated = True
                    service.save()
                    msg = ''.join([request.user.username,
                            ' deprecated \'',
                            service.name,'\' service'])
                    logger.info(msg)
                    make_log_entry(request.user.username,service,msg)
                    
                return redirect(reverse('services:index'))

    else:
        debug = 'first time'
        service_id = 0
        form = ServiceForm()
        link_formset = LinkFormSet(prefix='link')
        host_formset = HostFormSet(prefix='host')

    context = {'page': 'add', 'form':form, 
            'host_formset':host_formset,
            'link_formset':link_formset,
            'service_id':str(service_id),
            'debug':debug,
            'app_name': settings.APP_NAME}
    return render(request, 'services/add_bootstrap.html', context)

#def login(request):
#    return render(request, 'services/login.html')

@login_required
def clear_and_logout(request):
    # clear any locks by current user
    EditLock.objects.filter(username=request.user.username).delete()
    return redirect(reverse('account_logout'))

@login_required
def edit_sorry(request):
    context = {'app_name': settings.APP_NAME}
    return render(request, 'services/edit_sorry.html', context)

@login_required
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
def edit(request, service_id):
    """
    Make forms using existing data as initial data.
    """

    # TODO check for valid service_id ??
    service = Service.objects.get(pk=service_id)
    if service.deprecated:
        return redirect(reverse('services:index'))

    # clear any locks by current user
    EditLock.objects.filter(username=request.user.username).delete()
    # check for other locks
    locks = EditLock.objects.filter(service=service)
    if locks:
        # check timestamps?
        return redirect(reverse('services:edit_sorry'))
    else:
        EditLock.objects.create(service=service,
                username=request.user.username)

    init_data = Service.objects.filter(pk=service_id).values(
            'name', 'description', 'hostname', 'failover_process',
            'failover_last_tested', 'service_last_verified', 'dependencies',
            'lb', 'ha', 'otp','nagios')[0]
    form = ServiceForm(initial=init_data)


    init_data = service.link_set.values('url', 'description')
    if init_data:
        LinkFormSet = formset_factory(LinkForm, extra=0)
    else:
        LinkFormSet = formset_factory(LinkForm, extra=1)
    link_formset = LinkFormSet(initial=init_data, prefix='link')

    hosts = service.host_set.values()
    init_data = []
    for fields in hosts:
        # foreign key fields will have '_id' appended
        d = {'label':fields['label'], 
            'location_choice':fields['location_id'],
            'hostname':fields['hostname'],
            'ip_address':fields['ip_address'],
            'qualys' : fields['qualys'],
            'nagios' : fields['nagios'],
            'availability':fields['availability_id'],
            'support':fields['support_id'],
            'sys_admin_choice':fields['sys_admin_id'],
            'poc_primary_choice':fields['poc_primary_id'],
            'poc_backup_choice':fields['poc_backup_id'],
            'host_last_verified':fields['host_last_verified'],
            'note':fields['note']}
        init_data.append(d)
    HostFormSet = formset_factory(HostForm, extra=0)
    host_formset = HostFormSet(initial=init_data, prefix='host')
    privileged = False
    if request.user.username == 'grogers':
        privileged = True
    context = {'page': 'add', 'form':form, 
            'host_formset':host_formset,
            'link_formset':link_formset,
            'service_id':service_id,
            'privileged':privileged,
            'app_name': settings.APP_NAME
    }
    return render(request, 'services/add_bootstrap.html', context)

# event testing
@login_required
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
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
        events.append({'created':e.created,'name':e.name,'id':e.id,
                'description':e.description,'totals':{
                'hosts':num_hosts,
                'unchecked':unchecked,
                'in_progress':in_progress,
                'compliant':compliant,
                'na':na}
                #'unchecked':float(unchecked)/float(num_hosts)*100.0,}
                })

    context = {'page': 'events', 'events':events,
            'app_name': settings.APP_NAME}
    return render(request, 'services/events.html', context)

@login_required
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
def add_event(request):
    if request.POST:
        form = AddEventForm(request.POST)
        if form.is_valid():
            e = form.save()     # creates Event
            # make status entries for each host
            for h in Host.objects.filter(service__deprecated=False):
                hes = HostEventStatus(event=e,host=h,
                        status=HostEventStatus.UNCHECKED)
                hes.save()
                
            return redirect(reverse('services:events'))
    else:
        form = AddEventForm()

    context = {'page': 'events', 'form':form, 
            'app_name': settings.APP_NAME}
    return render(request, 'services/add_event.html', context)

@login_required
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
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
@user_passes_test(editors_check,login_url=reverse_lazy('services:unprivileged'))
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

def make_pdf(request):
    services = []
    for s in Service.objects.order_by('name'):
        services.append({'service': s, 'instances': s.instance_set.all()})
    
    context = {'services':services}
    return do_pdf('services/index.html', context)

def add2(request):
    ServiceFormSet = formset_factory(ServiceForm, extra=1)
    StaffFormSet = formset_factory(StaffForm, extra=3)
    SiteFormSet = formset_factory(SiteForm, extra=1)
    if request.POST:
        service_formset = ServiceFormSet(request.POST, prefix='service')
        #sform = ServiceForm(request.POST)
        iform = InstanceForm(request.POST)
        staff_formset = StaffFormSet(request.POST, prefix='staff')
        #site_form = SiteForm()
        site_formset = SiteFormSet(request.POST, prefix='site')
        new_entries = []
        if request.POST['service'] == '':
            service_formset[0].empty_permitted = False
            new_entries.append('service')
        if request.POST['sys_admin'] == '':
            staff_formset[0].empty_permitted = False
            new_entries.append('sys_admin')
        if request.POST['poc_primary'] == '':
            staff_formset[1].empty_permitted = False
            new_entries.append('poc_primary')
        if request.POST['poc_backup'] == '':
            staff_formset[2].empty_permitted = False
            new_entries.append('poc_backup')
        if request.POST['location'] == '':
            site_formset[0].empty_permitted = False
            new_entries.append('location')

        test = 'NOT VALID'
        if (service_formset.is_valid() and iform.is_valid() and 
                staff_formset.is_valid() and site_formset.is_valid()):
            test = 'VALID'
            instance = iform.save(commit=False)
            if 'service' in new_entries:
                service = service_formset[0].save()
                instance.service = service
            #instance.service = service
            if 'sys_admin' in new_entries:
                # check for duplicates?
                sys_admin = staff_formset[0].save()
                instance.sys_admin = sys_admin
            if 'poc_primary' in new_entries:
                # check for match with sys_admin
                staff = staff_formset[1].save(commit=False)
                if (staff.name == sys_admin.name and 
                        staff.email == sys_admin.email):
                    instance.poc_primary = sys_admin
                else:
                    staff.save()
                    instance.poc_primary = staff
            if 'poc_backup' in new_entries:
                staff = staff_formset[2].save()
                instance.poc_backup = staff
            if 'location' in new_entries:
                site = site_formset[0].save()
                instance.location = site
            instance.save()
    else:
        service_formset = ServiceFormSet(prefix='service')
        #sform = ServiceForm()
        iform = InstanceForm()
        #site_form = SiteForm()
        staff_formset = StaffFormSet(prefix='staff')
        site_formset = SiteFormSet(prefix='site')
        test = 'first'
        # you'll have staff-0-name and staff-0-email
    context = {
            #'sform': sform, 
            'service_formset': service_formset,
            'iform': iform, 
            'test': test,
            'staff_formset': staff_formset,
            'site_formset': site_formset,
            }
    return render(request, 'services/add.html', context)
