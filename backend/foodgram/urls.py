from django.contrib import admin
from django.urls import path
from django.urls.conf import include

from foodgram.settings import DEBUG
from api.urls import api


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(api)),
]

if DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls), name='debug_toolbar')
    ]
