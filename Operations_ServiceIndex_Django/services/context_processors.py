# myapp/context_processors.py
from .models import Misc_urls

def misc_urls_processor(request):
    # Create a dictionary to hold the URL mappings
    url_mapping = {}

    # Fetch all entries in the Misc_urls table
    misc_urls = Misc_urls.objects.all()

    # Populate the dictionary with names as keys and URLs as values
    for entry in misc_urls:
        url_mapping[entry.name] = entry.urls

    # Return the dictionary so it can be accessed in templates
    return {
        'MISC_URLS': url_mapping
    }