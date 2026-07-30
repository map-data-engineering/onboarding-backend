from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("application.urls")),
    # Frontend pages (served same-origin so the JS can call /api/ without CORS).
    path("", TemplateView.as_view(template_name="applicant/portal.html"), name="applicant-portal"),
    path("panel/", TemplateView.as_view(template_name="panel/index.html"), name="staff-panel"),
]

# Serve uploaded CVs during development.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
