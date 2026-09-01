from rest_framework.views import APIView
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from .models import User
from .serializers import (
    AdminLoginSerializer,
    OTPVerifySerializer,
    UserRegisterSerializer,
    UserLoginSerializer,
    ForgotPasswordSerializer,
    VerifyResetOTPSerializer,
    ResetPasswordSerializer,
    UserForgotPasswordSerializer,
    UserVerifyResetOTPSerializer,
    UserResetPasswordSerializer,
    UserProfileUpdateSerializer,
    UserChangePasswordSerializer,
)


class AdminLoginView(APIView):
    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserRegisterView(APIView):
    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()  # stages data + sends OTP, no user created yet
        return Response(
            {"message": "OTP sent to your email. Please verify to complete registration."},
            status=status.HTTP_200_OK
        )
    
class VerifyOTPView(APIView):
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.create_user()
        return Response(
            {"message": "Email verified. Account created successfully.", "id": user.id},
            status=status.HTTP_201_CREATED
        )

class UserLoginView(APIView):
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ForgotPasswordView(APIView):
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.send_otp()
            return Response(
                {'message': 'OTP sent to your email. It expires in 10 minutes.'},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyResetOTPView(APIView):
    def post(self, request):
        serializer = VerifyResetOTPSerializer(data=request.data)
        if serializer.is_valid():
            serializer.mark_verified()
            return Response(
                {'message': 'OTP verified. You may now reset your password.'},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResetPasswordView(APIView):
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.set_new_password()
            return Response(
                {'message': 'Password reset successfully.'},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserForgotPasswordView(APIView):
    def post(self, request):
        serializer = UserForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.send_otp()
            return Response(
                {'message': 'OTP sent to your email. It expires in 10 minutes.'},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserVerifyResetOTPView(APIView):
    def post(self, request):
        serializer = UserVerifyResetOTPSerializer(data=request.data)
        if serializer.is_valid():
            serializer.mark_verified()
            return Response(
                {'message': 'OTP verified successfully.'},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserResetPasswordView(APIView):
    def post(self, request):
        serializer = UserResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.set_new_password()
            return Response(
                {'message': 'Password reset successfully.'},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserBasicInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        username = f"{user.first_name} {user.last_name}".strip()
        if not username:
            username = user.email.split('@')[0]

        profile_picture = ''
        if user.profile_picture:
            profile_picture = request.build_absolute_uri(user.profile_picture.url)

        return Response(
            {
                'username': username,
                'email': user.email,
                'profile_picture': profile_picture,
            },
            status=status.HTTP_200_OK,
        )


class UserEditProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def patch(self, request):
        serializer = UserProfileUpdateSerializer(
            instance=request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        profile_picture_url = None
        if user.profile_picture:
            profile_picture_url = request.build_absolute_uri(user.profile_picture.url)

        return Response(
            {
                'message': 'Profile updated successfully.',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'profile_picture': profile_picture_url,
                },
            },
            status=status.HTTP_200_OK,
        )


class UserChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UserChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'message': 'Password changed successfully.'}, status=status.HTTP_200_OK)
    

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class GoogleLoginView(APIView):
    permission_classes = []  # public — no auth required

    def post(self, request):
        credential = request.data.get("credential")

        if not credential:
            return Response(
                {"error": "credential is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            idinfo = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
        except ValueError as e:
            return Response(
                {"error": f"Invalid Google token: {str(e)}"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        email = idinfo.get("email")
        first_name = idinfo.get("given_name", "")
        last_name = idinfo.get("family_name", "")

        if not email:
            return Response(
                {"error": "Email not returned by Google"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fits your AbstractBaseUser — no username field, email is USERNAME_FIELD
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "role": "USER",
                "is_active": True,
            }
        )

        # Edge case: account exists but was manually created — update name if empty
        if not created and not user.first_name:
            user.first_name = first_name
            user.last_name = last_name
            user.save(update_fields=["first_name", "last_name"])

        if not user.is_active:
            return Response(
                {"error": "Your account has been deactivated. Contact admin."},
                status=status.HTTP_403_FORBIDDEN,
            )

        tokens = get_tokens_for_user(user)

        return Response({
            "tokens": tokens,
            "user": {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
                "is_new_user": created,
            }
        }, status=status.HTTP_200_OK)