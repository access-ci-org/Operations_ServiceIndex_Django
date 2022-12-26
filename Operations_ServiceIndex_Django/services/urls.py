from django.urls import include, path, re_path

from services import views

app_name = 'services'
urlpatterns = [
    # these are all in 'services' namespace; to reference in template, use:
    #   {% url 'services:index' %}
    # or if there is a parameter to pass:
    #   {% url 'services:edit' 24 %} 
    path('', views.index, name="index"),
    path('add/', views.add_service, name="add_service"),
    re_path('^edit/(?P<service_id>\d+)$', views.edit_service, name="edit_service"),
    path('update/', views.update_service, name="update_service"),
    re_path('^hosts/(?P<order_field>\w+)$', views.hosts, name="hosts"),
    path('people/', views.people, name="people"),
    re_path('^edit_staff/(?P<staff_id>\d+)$', views.edit_staff, name="edit_staff"),
    #path('hosts_by_service/', views.hosts_by_service, name="hosts_by_service"),
    path('edit_sorry/', views.edit_sorry, name="edit_sorry"),
    path('export/', views.export, name="export"),
    path('custom/', views.custom, name="custom"),
    path('listing/', views.listing, name="listing"),
    path('login/', views.login, name="login"),
    path('log_listing/', views.log_listing, name="log_listing"),
    path('view_log/', views.view_log, name="view_log"),
    path('metrics/', views.metrics, name="metrics"),
    path('add_event/', views.add_event, name="add_event"),
    path('events/', views.events, name="events"),
    re_path('^event/(?P<event_id>\d+)$', views.event, name="event"),
    re_path('^update_event/(?P<hes_id>\d+)$', views.update_event, name="update_event"),
    path('api/hosts/', views.api_hosts, name="api_hosts"),
    path('clear_and_logout/', views.clear_and_logout, name='clear_and_logout'),
    path('unprivileged/', views.unprivileged, name="unprivileged"),
]
