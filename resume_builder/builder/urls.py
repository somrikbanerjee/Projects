from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('preview/', views.preview_fragment, name='preview'),
    path('save/', views.save_resume, name='save_resume'),
    path('download/', views.download_pdf, name='download_pdf'),
]
