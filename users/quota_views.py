from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.quota import QuotaManager


class QuotaView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated:
            quota = QuotaManager.get_ai_chat_quota(
                "user", str(request.user.pk), user=request.user
            )
        else:
            device_id = request.headers.get("X-Device-ID", "")
            if not device_id:
                return Response({"error": "X-Device-ID header required for anonymous users."}, status=400)
            quota = QuotaManager.get_ai_chat_quota("anon", device_id)

        return Response({"ai_chat": quota})
