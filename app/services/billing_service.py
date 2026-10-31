"""Billing, subscription management, minute tracking and plan catalog."""
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.call import Call
from app.models.enums import BillingCycle, PlanKey, SubscriptionStatus
from app.models.plan import MinutePack, Plan, Subscription


def minutes_for_call(duration_seconds: float | int | None) -> int:
    """Calculate billed minutes for a call duration: ceil(duration_seconds / 60).
    Rule is isolated here so it can be changed later without modifying callers."""
    if duration_seconds is None or duration_seconds <= 0:
        return 0
    return math.ceil(duration_seconds / 60)


class BillingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_plans(self) -> list[Plan]:
        """Public list of active platform plans."""
        return list(self.db.scalars(select(Plan).order_by(Plan.id)).all())

    def get_or_create_default_subscription(self, client_id: int) -> Subscription:
        """Find active subscription for client or initialize default growth plan."""
        sub = self.db.scalar(
            select(Subscription).where(
                Subscription.client_id == client_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        if sub is not None:
            return sub

        # Fallback to create default active growth subscription
        growth_plan = self.db.scalar(select(Plan).where(Plan.key == "growth"))
        if not growth_plan:
            growth_plan = Plan(
                key="growth",
                name="Growth",
                monthly_price=5700,
                yearly_price=66000,
                included_minutes=1000,
                max_call_minutes=5,
                is_custom=False,
            )
            self.db.add(growth_plan)
            self.db.flush()

        now = datetime.now(timezone.utc)
        sub = Subscription(
            client_id=client_id,
            plan_id=growth_plan.id,
            billing_cycle=BillingCycle.MONTHLY,
            status=SubscriptionStatus.ACTIVE,
            period_start=now,
            renews_on=now + timedelta(days=30),
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    @staticmethod
    def _summary(plan: Plan | None, cycle: str, renews_on: datetime | None,
                 minutes_limit: int, minutes_used: int) -> dict:
        plan_key = plan.key if plan else "growth"
        minutes_remaining = max(0, minutes_limit - minutes_used)
        usage_percent = (
            round((minutes_used / minutes_limit) * 100, 1) if minutes_limit > 0 else 0.0
        )
        if usage_percent >= 100:
            alert = "limit"
        elif usage_percent >= 80:
            alert = "warning"
        else:
            alert = "none"
        next_payment = (
            plan.yearly_price if cycle == "yearly" else plan.monthly_price
        ) if plan else None
        return {
            "plan": plan_key,
            "billing_cycle": cycle,
            "minutes_limit": minutes_limit,
            "minutes_used": minutes_used,
            "minutes_remaining": minutes_remaining,
            "usage_percent": usage_percent,
            "alert": alert,
            "renews_on": renews_on,
            "next_payment_amount": next_payment,
        }

    def get_billing_me(self, client_id: int, *, create_default: bool = True) -> dict:
        """Return billing breakdown: plan, cycle, limits, usage, alerts and renewal."""
        sub = self.db.scalar(
            select(Subscription).where(
                Subscription.client_id == client_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        if sub is None and create_default:
            sub = self.get_or_create_default_subscription(client_id)
        if sub is None:
            growth_plan = self.db.scalar(select(Plan).where(Plan.key == "growth"))
            return self._summary(growth_plan, "monthly", None, 0, 0)
        plan = self.db.get(Plan, sub.plan_id)
        plan_included = plan.included_minutes if plan else 1000

        # Sum minute packs added in the current period
        packs = self.db.scalars(
            select(MinutePack).where(
                MinutePack.client_id == client_id,
                MinutePack.created_at >= sub.period_start,
                MinutePack.created_at <= sub.renews_on,
            )
        ).all()
        extra_minutes = sum(p.minutes for p in packs)
        minutes_limit = plan_included + extra_minutes

        # Sum call minutes in current period
        calls = self.db.scalars(
            select(Call).where(
                Call.client_id == client_id,
                Call.created_at >= sub.period_start,
                Call.created_at <= sub.renews_on,
            )
        ).all()
        minutes_used = sum(minutes_for_call(c.duration) for c in calls)
        cycle_str = sub.billing_cycle.value if hasattr(sub.billing_cycle, "value") else str(sub.billing_cycle)
        return self._summary(plan, cycle_str, sub.renews_on, minutes_limit, minutes_used)

    def get_billing_for_clients(self, client_ids: list[int]) -> dict[int, dict]:
        """Batch the monitoring billing calculation without creating subscriptions."""
        if not client_ids:
            return {}
        subscriptions = self.db.scalars(
            select(Subscription)
            .where(
                Subscription.client_id.in_(client_ids),
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .order_by(Subscription.id)
        ).all()
        active_by_client = {}
        for subscription in subscriptions:
            active_by_client.setdefault(subscription.client_id, subscription)

        plans = self.db.scalars(select(Plan)).all()
        plans_by_id = {plan.id: plan for plan in plans}
        growth_plan = next((plan for plan in plans if plan.key == "growth"), None)
        period_filters = [
            and_(
                MinutePack.client_id == subscription.client_id,
                MinutePack.created_at >= subscription.period_start,
                MinutePack.created_at <= subscription.renews_on,
            )
            for subscription in active_by_client.values()
        ]
        extra_minutes = {}
        if period_filters:
            pack_rows = self.db.execute(
                select(MinutePack.client_id, MinutePack.minutes)
                .where(or_(*period_filters))
            ).all()
            for client_id, minutes in pack_rows:
                extra_minutes[client_id] = extra_minutes.get(client_id, 0) + minutes

        call_filters = [
            and_(
                Call.client_id == subscription.client_id,
                Call.created_at >= subscription.period_start,
                Call.created_at <= subscription.renews_on,
            )
            for subscription in active_by_client.values()
        ]
        minutes_used = {}
        if call_filters:
            call_rows = self.db.execute(
                select(Call.client_id, Call.duration).where(or_(*call_filters))
            ).all()
            for client_id, duration in call_rows:
                minutes_used[client_id] = (
                    minutes_used.get(client_id, 0) + minutes_for_call(duration)
                )

        results = {}
        for client_id in client_ids:
            subscription = active_by_client.get(client_id)
            if subscription is None:
                results[client_id] = self._summary(growth_plan, "monthly", None, 0, 0)
                continue
            plan = plans_by_id.get(subscription.plan_id)
            included = plan.included_minutes if plan else 1000
            cycle = (
                subscription.billing_cycle.value
                if hasattr(subscription.billing_cycle, "value")
                else str(subscription.billing_cycle)
            )
            results[client_id] = self._summary(
                plan, cycle, subscription.renews_on,
                included + extra_minutes.get(client_id, 0),
                minutes_used.get(client_id, 0),
            )
        return results
