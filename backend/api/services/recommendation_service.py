import logging
from typing import Any, Dict, List, Optional
from api.models import PriceSnapshot

logger = logging.getLogger(__name__)

HOURS_PER_MONTH = 730


class NoPriceDataError(RuntimeError):
    """Raised when no PriceSnapshot records exist to evaluate recommendations."""
    pass


def _resolve_region_snapshots(region: Optional[str]) -> List[PriceSnapshot]:
    """
    Finds PriceSnapshot records for the given region or closely matching equivalent multi-cloud regions.
    Falls back to all available snapshots if no regional match is found.
    """
    if not PriceSnapshot.objects.exists():
        raise NoPriceDataError("No PriceSnapshot records found in database. Run refresh_all_prices first.")

    if not region:
        return list(PriceSnapshot.objects.all())

    # Try exact match first
    exact_match = list(PriceSnapshot.objects.filter(region__iexact=region.strip()))
    if exact_match:
        return exact_match

    # Regional equivalence for Indian cloud regions
    region_lower = region.lower()
    india_keywords = ['mumbai', 'india', 'gujarat', 'bengaluru', 'asia-south', 'centralindia']
    if any(kw in region_lower for kw in india_keywords):
        india_regions = ['Asia Pacific (Mumbai)', 'centralindia', 'asia-south1']
        matched = list(PriceSnapshot.objects.filter(region__in=india_regions))
        if matched:
            return matched

    # Fallback to all available snapshots
    return list(PriceSnapshot.objects.all())


def _calculate_performance_score(c_vcpu: int, c_ram: float, req_vcpu: int, req_ram: float) -> tuple[float, float]:
    """
    Computes performance score and percentage headroom.
    Score peaks around 1.3-1.5x the requirement, then gently declines to avoid oversized waste.
    """
    vcpu_ratio = c_vcpu / max(1, req_vcpu)
    ram_ratio = c_ram / max(0.1, req_ram)
    avg_headroom = (vcpu_ratio + ram_ratio) / 2.0
    headroom_pct = round((avg_headroom - 1.0) * 100, 1)

    if avg_headroom < 1.0:
        # Under-provisioned (relaxed match path)
        perf_score = max(0.1, avg_headroom * 0.5)
    elif 1.0 <= avg_headroom <= 1.4:
        # Optimal headroom: scales from 0.50 up to 1.0
        perf_score = 0.50 + ((avg_headroom - 1.0) / 0.4) * 0.50
    else:
        # Oversized (>1.4x): flattens and gently declines to avoid unnecessary waste
        perf_score = max(0.5, 1.0 - (avg_headroom - 1.4) * 0.10)

    return round(perf_score, 4), headroom_pct


def _calculate_reliability_score(pricing_model: str) -> float:
    """Uses pricing model as a reliability / capacity commitment proxy."""
    model_lower = (pricing_model or '').lower()
    if 'reserved' in model_lower or 'committed' in model_lower:
        return 1.0
    if 'ondemand' in model_lower or 'consumption' in model_lower or 'payasyougo' in model_lower:
        return 0.85
    if 'spot' in model_lower or 'preemptible' in model_lower or 'low priority' in model_lower:
        return 0.40
    return 0.70


def _build_reasoning(
    candidate: PriceSnapshot,
    monthly_cost: float,
    req_vcpu: int,
    req_ram: float,
    headroom_pct: float,
    preference: str,
    runner_up: Optional[PriceSnapshot] = None,
    runner_up_cost: Optional[float] = None,
    matched_exactly: bool = True,
) -> str:
    """
    Constructs a dynamic, programmatic reasoning string from actual computed metrics.
    Never uses static placeholder or generic text.
    """
    parts = []

    # Headroom description
    if matched_exactly:
        headroom_desc = (
            f"provides {candidate.vcpu} vCPU / {candidate.memoryGiB:.1f} GB RAM against your estimated "
            f"need of {req_vcpu} vCPU / {req_ram:.1f} GB RAM, giving ~{headroom_pct}% headroom for traffic spikes"
        )
    else:
        headroom_desc = (
            f"provides {candidate.vcpu} vCPU / {candidate.memoryGiB:.1f} GB RAM as the closest available "
            f"capacity for your estimated need of {req_vcpu} vCPU / {req_ram:.1f} GB RAM"
        )

    # Comparative advantage against runner-up
    if runner_up and runner_up_cost is not None and runner_up_cost > 0:
        if monthly_cost < runner_up_cost:
            pct_cheaper = round(((runner_up_cost - monthly_cost) / runner_up_cost) * 100, 1)
            why_beat = (
                f"At ${monthly_cost:.2f}/mo, it is {pct_cheaper}% cheaper than the next closest option "
                f"({runner_up.provider} {runner_up.instanceType} at ${runner_up_cost:.2f}/mo) while satisfying all compute constraints"
            )
        else:
            cost_diff = round(monthly_cost - runner_up_cost, 2)
            why_beat = (
                f"Chosen for superior compute capacity and performance headroom per your '{preference}' preference, "
                f"outscoring {runner_up.provider} {runner_up.instanceType} (a ${cost_diff:.2f}/mo differential justified by throughput)"
            )
    else:
        why_beat = f"Ranked highest overall based on your '{preference}' weighting criteria."

    prefix = "" if matched_exactly else "Note: Exact resource requirements exceeded standard single-node boundaries; relaxed matching was applied. "
    return f"{prefix}{candidate.provider} {candidate.instanceType} (${monthly_cost:.2f}/mo) {headroom_desc}. {why_beat}."


def generate_recommendation(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Core recommendation engine.
    Filters candidate instances from PriceSnapshot, scores on cost, performance, and reliability,
    applies preference-based weighting, and returns the top recommendation with runner-ups.
    """
    req_vcpu = int(payload.get('vcpu', 2))
    req_ram = float(payload.get('ramGB', payload.get('ram', 4.0)))
    region = payload.get('region')
    preference = (payload.get('preference') or 'balanced').strip().lower()
    if preference not in {'cost', 'performance', 'balanced'}:
        preference = 'balanced'

    snapshots = _resolve_region_snapshots(region)

    # 1. FILTER: vcpu >= req_vcpu AND memoryGiB >= req_ram
    exact_candidates = [
        s for s in snapshots
        if s.vcpu >= req_vcpu and s.memoryGiB >= req_ram
    ]

    matched_exactly = True
    if exact_candidates:
        candidates = exact_candidates
    else:
        matched_exactly = False
        # Relax filter: pick candidates with smallest resource gap or highest available
        candidates = sorted(
            snapshots,
            key=lambda s: (abs(s.vcpu - req_vcpu) + abs(s.memoryGiB - req_ram), -s.vcpu, -s.memoryGiB)
        )[:10]

    # 2. SCORE candidates
    prices = [c.pricePerUnit for c in candidates]
    min_price = min(prices)
    max_price = max(prices)

    scored_candidates = []
    for c in candidates:
        # Cost score: 0 to 1 (lower price = higher score)
        if max_price == min_price:
            cost_score = 1.0
        else:
            cost_score = (max_price - c.pricePerUnit) / (max_price - min_price)

        perf_score, headroom_pct = _calculate_performance_score(c.vcpu, c.memoryGiB, req_vcpu, req_ram)
        rel_score = _calculate_reliability_score(c.pricingModel)

        # 3. WEIGHTING
        if preference == 'cost':
            w_cost, w_perf, w_rel = 0.60, 0.25, 0.15
        elif preference == 'performance':
            w_cost, w_perf, w_rel = 0.20, 0.60, 0.20
        else:  # balanced
            w_cost, w_perf, w_rel = 0.34, 0.33, 0.33

        final_score = round(w_cost * cost_score + w_perf * perf_score + w_rel * rel_score, 4)
        monthly_cost = round(c.pricePerUnit * HOURS_PER_MONTH, 2)

        scored_candidates.append({
            'candidate': c,
            'monthlyCostUsd': monthly_cost,
            'headroomPct': headroom_pct,
            'score': final_score,
        })

    # Sort descending by finalScore, then ascending by monthlyCostUsd
    scored_candidates.sort(key=lambda item: (-item['score'], item['monthlyCostUsd']))

    best_item = scored_candidates[0]
    runner_up_item = scored_candidates[1] if len(scored_candidates) > 1 else None

    # Generate reasoning for top recommendation
    best_reasoning = _build_reasoning(
        candidate=best_item['candidate'],
        monthly_cost=best_item['monthlyCostUsd'],
        req_vcpu=req_vcpu,
        req_ram=req_ram,
        headroom_pct=best_item['headroomPct'],
        preference=preference,
        runner_up=runner_up_item['candidate'] if runner_up_item else None,
        runner_up_cost=runner_up_item['monthlyCostUsd'] if runner_up_item else None,
        matched_exactly=matched_exactly,
    )

    recommended_dict = {
        'provider': best_item['candidate'].provider,
        'instanceType': best_item['candidate'].instanceType,
        'monthlyCostUsd': best_item['monthlyCostUsd'],
        'vcpu': best_item['candidate'].vcpu,
        'memoryGiB': float(best_item['candidate'].memoryGiB),
        'pricingModel': best_item['candidate'].pricingModel,
        'score': best_item['score'],
        'reasoning': best_reasoning,
    }

    # Format top 2-3 alternatives
    alternatives = []
    for item in scored_candidates[1:4]:
        c = item['candidate']
        alt_reasoning = _build_reasoning(
            candidate=c,
            monthly_cost=item['monthlyCostUsd'],
            req_vcpu=req_vcpu,
            req_ram=req_ram,
            headroom_pct=item['headroomPct'],
            preference=preference,
            runner_up=best_item['candidate'],
            runner_up_cost=best_item['monthlyCostUsd'],
            matched_exactly=matched_exactly,
        )
        alternatives.append({
            'provider': c.provider,
            'instanceType': c.instanceType,
            'monthlyCostUsd': item['monthlyCostUsd'],
            'vcpu': c.vcpu,
            'memoryGiB': float(c.memoryGiB),
            'pricingModel': c.pricingModel,
            'score': item['score'],
            'reasoning': alt_reasoning,
        })

    return {
        'recommended': recommended_dict,
        'alternatives': alternatives,
        'matchedExactly': matched_exactly,
    }
