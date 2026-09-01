from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.cache import cache
from django.core.mail import send_mail
import random

User = get_user_model()


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        user = authenticate(email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid credentials")
        if user.role != 'ADMIN':
            raise serializers.ValidationError("Not authorized as admin")

        refresh = RefreshToken.for_user(user)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'password']
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True},
            'password': {'required': True},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def save(self):
        """Stage data + send OTP. Does NOT create the user yet."""
        data = self.validated_data
        email = data['email']

        otp = str(random.randint(100000, 999999))

        # Store registration payload + OTP in cache for 10 minutes
        # Key: pending_user:<email>
        cache.set(f'pending_user:{email}', {
            'email': email,
            'first_name': data['first_name'],
            'last_name': data['last_name'],
            'password': data['password'],   # passed raw; create_user() will hash it
            'otp': otp,
        }, timeout=600)  # 10 minutes

        send_mail(
            subject='Verify your email',
            message=f'Your OTP is: {otp}\n\nExpires in 10 minutes.',
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[email],
            fail_silently=False,
        )


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        email = attrs['email']
        otp = attrs['otp']

        pending = cache.get(f'pending_user:{email}')

        if not pending:
            raise serializers.ValidationError(
                "OTP expired or no pending registration found for this email."
            )
        if pending['otp'] != otp:
            raise serializers.ValidationError("Invalid OTP.")

        attrs['pending'] = pending
        return attrs

    def create_user(self):
        pending = self.validated_data['pending']
        email = pending['email']

        user = User.objects.create_user(
            email=pending['email'],
            password=pending['password'],
            first_name=pending['first_name'],
            last_name=pending['last_name'],
            role='USER',
        )

        cache.delete(f'pending_user:{email}')  # clean up
        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        user = authenticate(email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid credentials")
        if user.role != 'USER':
            raise serializers.ValidationError("Not authorized as user")
        if not user.is_active:
            raise serializers.ValidationError("Your account has been deactivated. Contact admin.")

        refresh = RefreshToken.for_user(user)

        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
            }
        }


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'profile_picture', 'role', 'is_active']


class UserProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=50)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=50)
    email = serializers.EmailField(required=False)
    profile_picture = serializers.FileField(required=False)

    def validate_email(self, value):
        user = self.context['request'].user
        if User.objects.filter(email=value).exclude(id=user.id).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def update(self, instance, validated_data):
        # Update only provided, non-empty values. Missing/empty values are ignored.
        if 'first_name' in validated_data and validated_data['first_name'] != '':
            instance.first_name = validated_data['first_name']
        if 'last_name' in validated_data and validated_data['last_name'] != '':
            instance.last_name = validated_data['last_name']
        if 'email' in validated_data and validated_data['email'] != '':
            instance.email = validated_data['email']
        if 'profile_picture' in validated_data and validated_data['profile_picture']:
            instance.profile_picture = validated_data['profile_picture']

        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Password reset (3-step: send OTP → verify OTP → set new password)
# ---------------------------------------------------------------------------
class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        user = User.objects.filter(email=value).first()
        if not user:
            raise serializers.ValidationError("No account found with this email.")
        if user.role != 'ADMIN':
            raise serializers.ValidationError("Password reset is only available for admin accounts.")
        return value

    def send_otp(self):
        email = self.validated_data['email']
        otp = str(random.randint(100000, 999999))
        cache.set(f'pwd_reset_otp:{email}', otp, timeout=600)       # 10 min
        cache.delete(f'pwd_reset_verified:{email}')                  # clear any prior verified flag
        send_mail(
            subject='Password Reset OTP',
            message=f'Your password reset OTP is: {otp}\n\nExpires in 10 minutes.',
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )


class VerifyResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        email = attrs['email']
        otp = attrs['otp']
        cached_otp = cache.get(f'pwd_reset_otp:{email}')
        if not cached_otp:
            raise serializers.ValidationError("OTP expired or not requested.")
        if cached_otp != otp:
            raise serializers.ValidationError("Invalid OTP.")
        return attrs

    def mark_verified(self):
        email = self.validated_data['email']
        cache.delete(f'pwd_reset_otp:{email}')          # consume the OTP
        cache.set(f'pwd_reset_verified:{email}', True, timeout=600)  # 10 min window to reset


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if not cache.get(f'pwd_reset_verified:{value}'):
            raise serializers.ValidationError("OTP not verified or session expired.")
        return value

    def set_new_password(self):
        email = self.validated_data['email']
        new_password = self.validated_data['new_password']
        user = User.objects.get(email=email)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        cache.delete(f'pwd_reset_verified:{email}')


# ---------------------------------------------------------------------------
# User password reset (3-step: send OTP -> verify OTP -> set new password)
# ---------------------------------------------------------------------------
class UserForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        user = User.objects.filter(email=value).first()
        if not user:
            raise serializers.ValidationError("No user found with this email.")
        if user.role != 'USER':
            raise serializers.ValidationError("This endpoint is only for normal users.")
        return value

    def send_otp(self):
        email = self.validated_data['email']
        otp = str(random.randint(100000, 999999))
        cache.set(f'user_pwd_reset_otp:{email}', otp, timeout=600)
        cache.delete(f'user_pwd_reset_verified:{email}')
        send_mail(
            subject='User Password Reset OTP',
            message=f'Your password reset OTP is: {otp}\n\nExpires in 10 minutes.',
            from_email=None,
            recipient_list=[email],
            fail_silently=False,
        )


class UserVerifyResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate(self, attrs):
        email = attrs['email']
        otp = attrs['otp']
        cached_otp = cache.get(f'user_pwd_reset_otp:{email}')

        if not cached_otp:
            raise serializers.ValidationError("OTP expired or not requested.")
        if cached_otp != otp:
            raise serializers.ValidationError("Invalid OTP.")

        return attrs

    def mark_verified(self):
        email = self.validated_data['email']
        cache.delete(f'user_pwd_reset_otp:{email}')
        cache.set(f'user_pwd_reset_verified:{email}', True, timeout=600)


class UserResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        email = attrs['email']
        new_password = attrs['new_password']
        confirm_password = attrs['confirm_password']

        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})

        if not cache.get(f'user_pwd_reset_verified:{email}'):
            raise serializers.ValidationError({"email": "OTP not verified or session expired."})

        user = User.objects.filter(email=email, role='USER').first()
        if not user:
            raise serializers.ValidationError({"email": "No user found with this email."})

        attrs['user'] = user
        return attrs

    def set_new_password(self):
        email = self.validated_data['email']
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        cache.delete(f'user_pwd_reset_verified:{email}')


class UserChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        user = self.context['request'].user
        current_password = attrs['current_password']
        new_password = attrs['new_password']
        confirm_new_password = attrs['confirm_new_password']

        if not user.check_password(current_password):
            raise serializers.ValidationError({'current_password': 'Current password is incorrect.'})

        if new_password != confirm_new_password:
            raise serializers.ValidationError({'confirm_new_password': 'New passwords do not match.'})

        return attrs

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user