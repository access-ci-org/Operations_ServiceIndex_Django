# myapp/context_processors.py
from Operations_ServiceIndex_Django.services.models import Tags_Loc

def tags_loc_processor(request):
    tags_loc = Tags_Loc.objects.first()
    return {
        'TAGS_LOC': tags_loc.loc_url if tags_loc else '',
    }