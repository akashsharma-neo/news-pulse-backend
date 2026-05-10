"""
NewsPulse digest views — subscription management and unsubscribe.
"""

import logging

from django.core.mail import send_mail
from django.conf import settings
from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import EmailSubscriber
from .serializers import SubscribeSerializer, UnsubscribeSerializer, EmailSubscriberSerializer
from .tasks import generate_daily_digest_task

logger = logging.getLogger(__name__)


class SubscribeView(generics.CreateAPIView):
    """Allow users to subscribe to the daily digest.

    POST /api/digest/subscribe/
    Body: { "email": "user@example.com", "tabs": ["india", "sports"] }
    """

    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = SubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        tabs = serializer.validated_data.get("tabs", [])

        subscriber, created = EmailSubscriber.objects.get_or_create(
            email=email,
            defaults={"tabs": tabs, "is_active": True},
        )

        if not created and not subscriber.is_active:
            subscriber.is_active = True
            subscriber.tabs = tabs
            subscriber.save(update_fields=["is_active", "tabs", "updated_at"])

        if created:
            try:
                send_mail(
                    subject="Welcome to NewsPulse Daily Digest",
                    message=(
                        f"Thanks for subscribing with {email}!\n\n"
                        f"You'll receive the top stories from: {', '.join(tabs) if tabs else 'all tabs'}.\n\n"
                        f"To unsubscribe, visit:\n"
                        f"{settings.BASE_URL}/api/digest/unsubscribe/?token={subscriber.unsubscribe_token}"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.warning("Welcome email failed for %s: %s", email, e)

        return Response(
            EmailSubscriberSerializer(subscriber).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class UnsubscribeView(generics.RetrieveAPIView):
    """Unsubscribe via token.

    GET /api/digest/unsubscribe/?token=<uuid>
    Deactivates the subscriber and sends a confirmation email.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        token = request.query_params.get("token")
        if not token:
            return Response(
                {"error": "token is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            subscriber = EmailSubscriber.objects.get(unsubscribe_token=token, is_active=True)
        except EmailSubscriber.DoesNotExist:
            return Response(
                {"error": "Invalid or already unsubscribed token"},
                status=status.HTTP_404_NOT_FOUND,
            )

        subscriber.is_active = False
        subscriber.save(update_fields=["is_active", "updated_at"])

        try:
            send_mail(
                subject="NewsPulse Digest Unsubscribed",
                message=f"You have been unsubscribed from the daily digest.\n\nEmail: {subscriber.email}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[subscriber.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.warning("Unsubscribe confirmation email failed for %s: %s", subscriber.email, e)

        return Response(
            {"message": "Successfully unsubscribed"},
            status=status.HTTP_200_OK,
        )


class ResendDigestView(generics.GenericAPIView):
    """Manually trigger a digest send (admin/development use).

    POST /api/digest/resend/
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        result = generate_daily_digest_task.delay()
        return Response(
            {"message": "Digest task dispatched", "task_id": result.id},
            status=status.HTTP_202_ACCEPTED,
        )
