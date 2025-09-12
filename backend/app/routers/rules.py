from fastapi import APIRouter
from ..models import RulesExplanation
from ..analytics.rules import evaluate_rules

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/{symbol}", response_model=RulesExplanation)
async def get_rules(symbol: str):
    traffic, reasons = await evaluate_rules(symbol.upper())
    return RulesExplanation(traffic_light=traffic, reasons=reasons)
