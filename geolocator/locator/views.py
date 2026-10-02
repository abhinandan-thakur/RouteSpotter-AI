import json

import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import RoutePlanningError, build_route_plan


@csrf_exempt
@require_POST
def route_plan(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)

    start = payload.get("start") if isinstance(payload, dict) else None
    finish = payload.get("finish") if isinstance(payload, dict) else None

    if not isinstance(start, str) or not start.strip() or not isinstance(finish, str) or not finish.strip():
        return JsonResponse({"error": "Provide non-empty 'start' and 'finish' location strings."}, status=400)

    try:
        return JsonResponse(build_route_plan(start.strip(), finish.strip()))
    except RoutePlanningError as error:
        return JsonResponse({"error": str(error)}, status=422)
    except requests.RequestException:
        return JsonResponse({"error": "A geocoding or routing service is temporarily unavailable."}, status=502)
