from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('set-budget/', views.set_budget, name='set_budget'),
    path('set-budget/<int:year>/<int:month>/', views.set_budget, name='set_budget_month'),
    path('history/', views.history, name='history'),
    path('settings/', views.app_settings, name='app_settings'),
    path('api/predict/', views.api_predict, name='api_predict'),
    path('api/detect-location/', views.api_detect_location, name='api_detect_location'),
    path('delete/<int:year>/<int:month>/', views.delete_budget, name='delete_budget'),
]
