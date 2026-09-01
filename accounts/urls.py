from django.urls import path
from .views import (
    AdminLoginView,
    GoogleLoginView,
    UserRegisterView,
    UserLoginView,
    VerifyOTPView,
    ForgotPasswordView,
    VerifyResetOTPView,
    ResetPasswordView,
    UserForgotPasswordView,
    UserVerifyResetOTPView,
    UserResetPasswordView,
    UserBasicInfoView,
    UserEditProfileView,
    UserChangePasswordView,
)

urlpatterns = [
    path('admin/login/', AdminLoginView.as_view(), name='admin-login'),
    path('register/', UserRegisterView.as_view(), name='user-register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('login/', UserLoginView.as_view(), name='user-login'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('verify-reset-otp/', VerifyResetOTPView.as_view(), name='verify-reset-otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('user/forgot-password/', UserForgotPasswordView.as_view(), name='user-forgot-password'),
    path('user/verify-reset-otp/', UserVerifyResetOTPView.as_view(), name='user-verify-reset-otp'),
    path('user/reset-password/', UserResetPasswordView.as_view(), name='user-reset-password'),
    path('user/me/', UserBasicInfoView.as_view(), name='user-basic-info'),
    path('user/edit-profile/', UserEditProfileView.as_view(), name='user-edit-profile'),
    path('user/change-password/', UserChangePasswordView.as_view(), name='user-change-password'),
    path("auth/google/", GoogleLoginView.as_view(), name="google-login"),
]