from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import LoginSerializer, RegisterSerializer

WRONG_CREDENTIALS = {"detail": "Email or password is wrong."}


class RegisterView(APIView):
    """Creates a user and logs them in, in one request — the spec settles
    that registering has no separate confirmation step. See
    specs/player-accounts-plan.md, D6."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="register",
        tags=["Account"],
        summary="Create an account",
        description=(
            "Create a player account with an email, password and public display name, "
            "and start a browser session. To play through the API you also need a "
            "token, which the game's operator issues for the account."
        ),
        request=RegisterSerializer,
        responses={201: inline_serializer("RegisteredName", {"display_name": serializers.CharField()}), 400: OpenApiResponse(description="Email already registered, or a field is invalid.")},
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response({"display_name": user.display_name}, status=201)


class LoginView(APIView):
    """A wrong password and an unknown email return the same message — see
    specs/player-accounts-plan.md, D7. Do not branch on which case it was."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(WRONG_CREDENTIALS, status=400)

        login(request, user)
        return Response({"display_name": user.display_name}, status=200)


class LogoutView(APIView):
    """Idempotent: logging out when already logged out is still a 204, not
    an error."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="logout",
        tags=["Account"],
        summary="End the browser session",
        description=(
            "Ends a browser session. It does nothing to an API token: a token is "
            "revoked only by the game's operator. Always 204."
        ),
        request=None,
        responses={204: None},
    )
    def post(self, request):
        logout(request)
        return Response(status=204)
