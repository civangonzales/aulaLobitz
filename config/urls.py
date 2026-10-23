"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from academico.forms import EmailAuthenticationForm
from academico.presentation.views import protected_media

admin.site.has_permission = lambda request: (
    request.user.is_active and request.user.is_superuser
    and request.user.email.lower() == 'civangonzales@gmail.com'
)
admin.site.site_header = 'aulaLobitz · Administración'
admin.site.site_title = 'aulaLobitz'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html', authentication_form=EmailAuthenticationForm), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/password/reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('accounts/password/reset/sent/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('accounts/password/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/password/reset/complete/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
    path('media/<path:file_path>', protected_media, name='protected_media'),
    path('', include('academico.urls')),
]
