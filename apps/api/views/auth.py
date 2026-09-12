from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..permissions import IsEmployeeUser


class ObtainEmployeeTokenView(APIView):
    """
    Exchange employee_code + password for a DRF Token used on write endpoints.

    ``Authorization: Token <key>``
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        employee_code = (request.data.get("employee_code") or "").strip()
        password = request.data.get("password") or ""
        if not employee_code or not password:
            return Response(
                {"detail": "employee_code and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request, username=employee_code, password=password)
        if user is None or not user.is_active:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "employee_code": user.employee_code,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        )


class RevokeEmployeeTokenView(APIView):
    """Delete the caller's token (logout for API clients)."""

    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated, IsEmployeeUser]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
