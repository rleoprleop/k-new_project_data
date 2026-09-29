from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "generated"

TABLE_NAMES = [
    "users", "families", "bundle_discount_compositions", "plans", "age_benefits",
    "plan_age_benefits", "additional_services", "plan_benefits", "discounts",
    "internet_bundle_discount_rules", "premium_family_discount_rules",
    "user_discounts", "user_services", "content_usage",
]

EXPECTED_COLUMNS = {
    "users": ["user_id", "name", "age", "gender", "subscription_start_date", "current_plan_id", "family_id"],
    "families": [
        "family_id", "has_bundle", "bundle_type", "has_kt_internet",
        "internet_product_group", "internet_contract_months", "internet_status", "bundle_discount_method",
        "total_discount_allocation_method",
        "internet_benefit_discount_id",
    ],
    "bundle_discount_compositions": [
        "bundle_composition_id", "family_id", "component_type", "user_id",
        "component_role", "status", "start_date", "end_date",
    ],
    "plans": ["plan_id", "plan_name", "plan_family", "monthly_fee", "network_type"],
    "discounts": [
        "discount_id", "policy_domain", "benefit_code", "discount_name",
    ],
    "internet_bundle_discount_rules": [
        "internet_bundle_rule_id", "discount_id", "bundle_discount_method",
        "internet_product_group", "contract_months", "discount_target", "discount_amount",
    ],
    "premium_family_discount_rules": [
        "premium_family_rule_id", "discount_id", "benefit_type", "minimum_plan_fee",
        "guardian_minimum_plan_fee", "enrollment_min_age", "enrollment_max_age",
        "benefit_end_age", "discount_rate", "discount_amount",
    ],
    "user_discounts": [
        "user_discount_id", "user_id", "bundle_composition_id", "discount_id",
        "status", "start_date", "end_date",
    ],
    "content_usage": [
        "content_usage_id", "user_id", "usage_date", "content_category",
        "content_detail", "data_usage_mb",
    ],
}

# 생성기 내부 검증에는 사용할 수 있지만 최종 CSV에는 포함하지 않는 사용자 계산값.
INTERNAL_ONLY_USER_COLUMNS = {
    "current_total_discount_amount",
    "estimated_monthly_bill",
    "potential_family_discount",
}

pd.set_option("display.max_rows", 200)
pd.set_option("display.max_columns", 100)
pd.set_option("display.width", 180)


def section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def subsection(title: str) -> None:
    print("\n" + "-" * 80)
    print(title)
    print("-" * 80)


def load_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for name in TABLE_NAMES:
        path = DATA_DIR / f"{name}.csv"
        if not path.exists():
            if name == "content_usage":
                partition_paths = content_partition_paths()
                if partition_paths:
                    print(
                        f"[INFO] content_usage 일별 파티션 {len(partition_paths):,}개를 "
                        "스트리밍 검사합니다"
                    )
                    continue
            print(f"[WARN] 파일 없음: {path}")
            continue
        tables[name] = pd.read_csv(path, low_memory=False)
    return tables


def content_partition_paths() -> list[Path]:
    return sorted(
        (DATA_DIR / "raw" / "content_usage").glob("event_date=*/part-*.csv")
    )


def value_distribution(df: pd.DataFrame, column: str, top_n: int = 30) -> None:
    if column not in df.columns:
        return
    result = pd.DataFrame({
        "count": df[column].value_counts(dropna=False),
        "pct": (df[column].value_counts(dropna=False, normalize=True) * 100).round(2),
    })
    print(f"\n[{column}]")
    print(result.head(top_n).to_string())


def numeric_distribution(df: pd.DataFrame, columns: list[str]) -> None:
    available = [column for column in columns if column in df.columns]
    if not available:
        return
    numeric = df[available].apply(pd.to_numeric, errors="coerce")
    print(numeric.describe(percentiles=[0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]).T.round(2).to_string())


def check_output_schema(tables: dict[str, pd.DataFrame]) -> None:
    section("1. 최종 Output 스키마·테이블 현황")
    rows = []
    partition_paths = content_partition_paths()
    for name in TABLE_NAMES:
        df = tables.get(name)
        partition_columns: list[str] = []
        if name == "content_usage" and df is None and partition_paths:
            partition_columns = list(pd.read_csv(partition_paths[0], nrows=0).columns)
        actual_columns = list(df.columns) if df is not None else partition_columns
        missing = [
            col for col in EXPECTED_COLUMNS.get(name, [])
            if col not in actual_columns
        ]
        internal_leaks = (
            [] if name != "users" or df is None
            else sorted(INTERNAL_ONLY_USER_COLUMNS & set(df.columns))
        )
        is_partitioned_content = name == "content_usage" and bool(partition_columns)
        rows.append({
            "table": name,
            "loaded": df is not None or is_partitioned_content,
            "rows": len(df) if df is not None else ("streamed" if is_partitioned_content else 0),
            "columns": len(actual_columns),
            "missing_expected_columns": ", ".join(missing),
            "internal_only_columns_in_output": ", ".join(internal_leaks),
        })
    print(pd.DataFrame(rows).to_string(index=False))
    stale = [name for name in ["daily_usage.csv", "family_relationships.csv"] if (DATA_DIR / name).exists()]
    if stale:
        print("\n[NOTE] 이전 실행의 잔존 파일입니다. 새 output에는 생성하지 않습니다: " + ", ".join(stale))


def check_user_and_plan_distribution(tables: dict[str, pd.DataFrame]) -> None:
    if not {"users", "plans"}.issubset(tables):
        return
    users = tables["users"]
    plans = tables["plans"]
    merged = users.merge(plans, left_on="current_plan_id", right_on="plan_id", how="left", validate="many_to_one")
    section("2. 사용자·요금제 분포")
    value_distribution(users, "gender")
    value_distribution(merged, "plan_name", top_n=50)
    value_distribution(merged, "plan_family")
    value_distribution(merged, "network_type")
    value_distribution(merged.assign(is_choice=merged["plan_family"].isin(["CHOICE", "CHOICE_DOUBLE"])), "is_choice")
    subsection("사용자 현재 요금제 월정액")
    numeric_distribution(merged, ["monthly_fee"])
    age = pd.to_numeric(users["age"], errors="coerce")
    age_group = pd.cut(age, bins=[-1, 9, 19, 29, 39, 49, 59, 69, 79, 200],
                       labels=["0-9", "10-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"])
    print("\n[연령대]")
    print(pd.DataFrame({"count": age_group.value_counts(sort=False), "pct": (age_group.value_counts(sort=False) / len(users) * 100).round(2)}).to_string())


def check_usage_distribution(tables: dict[str, pd.DataFrame]) -> None:
    if "content_usage" not in tables:
        partition_paths = content_partition_paths()
        if partition_paths:
            check_partitioned_usage_distribution(partition_paths, tables)
        return
    content = tables["content_usage"].copy()
    content["data_usage_mb"] = pd.to_numeric(content["data_usage_mb"], errors="coerce")
    daily = content.groupby(["user_id", "usage_date"], as_index=False)["data_usage_mb"].sum().rename(columns={"data_usage_mb": "total_data_mb"})
    section("3. 콘텐츠 사용량 및 파생 일별 사용량")
    subsection("콘텐츠 카테고리별 사용량")
    category = content.groupby("content_category")["data_usage_mb"].agg(["count", "sum", "mean", "median"]).sort_values("sum", ascending=False)
    category["total_gb"] = category["sum"] / 1024
    category["share_pct"] = category["sum"] / category["sum"].sum() * 100
    print(category[["count", "total_gb", "share_pct", "mean", "median"]].round(2).to_string())
    subsection("콘텐츠 상세분류별 사용량")
    detail = content.groupby(["content_category", "content_detail"])["data_usage_mb"].agg(
        ["count", "sum", "mean", "median"]
    ).sort_values("sum", ascending=False)
    detail["total_gb"] = detail["sum"] / 1024
    detail["share_pct"] = detail["sum"] / detail["sum"].sum() * 100
    print(detail[["count", "total_gb", "share_pct", "mean", "median"]].round(2).to_string())
    subsection("content_usage에서 집계한 일별 사용량")
    numeric_distribution(daily, ["total_data_mb"])
    dates = pd.to_datetime(daily["usage_date"], errors="coerce")
    print(f"\n기간: {dates.min().date()} ~ {dates.max().date()} / 고유 날짜 수: {dates.nunique():,}")
    monthly_gb = daily.groupby("user_id")["total_data_mb"].mean() * 30 / 1024
    print("\n[사용자별 30일 환산 데이터 GB]")
    print(monthly_gb.describe(percentiles=[0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]).round(2).to_string())
    grain = ["user_id", "usage_date", "content_category", "content_detail"]
    print(f"\ncontent_usage 복합 grain 중복: {content.duplicated(grain).sum():,}건")


def check_partitioned_usage_distribution(
    partition_paths: list[Path], tables: dict[str, pd.DataFrame]
) -> None:
    user_ids = set(tables["users"]["user_id"].astype(str)) if "users" in tables else set()
    category_parts: list[pd.DataFrame] = []
    detail_parts: list[pd.DataFrame] = []
    daily_values: list[np.ndarray] = []
    user_total: dict[str, float] = {}
    user_days: dict[str, int] = {}
    total_rows = 0
    duplicate_grain = 0
    duplicate_ids = 0
    invalid_user_refs = 0
    null_rows = 0
    non_positive_rows = 0
    partition_dates: list[str] = []

    for index, partition_path in enumerate(partition_paths, start=1):
        frame = pd.read_csv(partition_path, low_memory=False)
        missing = [
            column for column in EXPECTED_COLUMNS["content_usage"]
            if column not in frame.columns
        ]
        if missing:
            raise ValueError(f"필수 컬럼 누락 {missing}: {partition_path}")
        partition_date = partition_path.parent.name.removeprefix("event_date=")
        actual_dates = frame["usage_date"].astype(str).unique()
        if len(actual_dates) != 1 or actual_dates[0] != partition_date:
            raise ValueError(f"파티션 날짜와 usage_date가 다릅니다: {partition_path}")
        partition_dates.append(partition_date)

        frame["data_usage_mb"] = pd.to_numeric(frame["data_usage_mb"], errors="coerce")
        total_rows += len(frame)
        null_rows += int(frame[EXPECTED_COLUMNS["content_usage"]].isna().any(axis=1).sum())
        non_positive_rows += int((frame["data_usage_mb"] <= 0).sum())
        duplicate_ids += int(frame["content_usage_id"].duplicated().sum())
        duplicate_grain += int(frame.duplicated(
            ["user_id", "usage_date", "content_category", "content_detail"]
        ).sum())
        if user_ids:
            invalid_user_refs += int((~frame["user_id"].astype(str).isin(user_ids)).sum())

        category_parts.append(
            frame.groupby("content_category")["data_usage_mb"]
            .agg(["count", "sum"])
        )
        detail_parts.append(
            frame.groupby(["content_category", "content_detail"])["data_usage_mb"]
            .agg(["count", "sum"])
        )
        daily = frame.groupby("user_id")["data_usage_mb"].sum()
        daily_values.append(daily.to_numpy(dtype=float))
        for user_id, amount in daily.items():
            key = str(user_id)
            user_total[key] = user_total.get(key, 0.0) + float(amount)
            user_days[key] = user_days.get(key, 0) + 1

        if index % 50 == 0 or index == len(partition_paths):
            print(
                f"[INFO] content partition check: {index:,}/{len(partition_paths):,}, "
                f"rows={total_rows:,}"
            )

    parsed_dates = pd.to_datetime(pd.Series(partition_dates), errors="raise")
    expected_dates = pd.date_range(parsed_dates.min(), parsed_dates.max(), freq="D")
    continuous_dates = len(expected_dates) == len(parsed_dates) and set(expected_dates) == set(parsed_dates)
    if not continuous_dates:
        raise ValueError("content_usage 파티션 날짜가 연속적이지 않습니다")

    category = pd.concat(category_parts).groupby(level=0).sum().sort_values("sum", ascending=False)
    category["total_gb"] = category["sum"] / 1024
    category["share_pct"] = category["sum"] / category["sum"].sum() * 100
    category["mean"] = category["sum"] / category["count"]
    detail = pd.concat(detail_parts).groupby(level=[0, 1]).sum().sort_values("sum", ascending=False)
    detail["total_gb"] = detail["sum"] / 1024
    detail["share_pct"] = detail["sum"] / detail["sum"].sum() * 100
    detail["mean"] = detail["sum"] / detail["count"]
    daily_array = np.concatenate(daily_values)
    monthly_gb = pd.Series({
        user_id: total / user_days[user_id] * 30 / 1024
        for user_id, total in user_total.items()
    })

    section("3. 콘텐츠 사용량 및 파생 일별 사용량 — 파티션 스트리밍")
    subsection("콘텐츠 카테고리별 사용량")
    print(category[["count", "total_gb", "share_pct", "mean"]].round(2).to_string())
    subsection("콘텐츠 상세분류별 사용량")
    print(detail[["count", "total_gb", "share_pct", "mean"]].round(2).to_string())
    subsection("content_usage에서 집계한 일별 사용량")
    print(pd.Series(daily_array).describe(
        percentiles=[0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]
    ).round(2).to_string())
    print(
        f"\n기간: {parsed_dates.min().date()} ~ {parsed_dates.max().date()} / "
        f"고유 날짜 수: {parsed_dates.nunique():,} / 행 수: {total_rows:,}"
    )
    print("\n[사용자별 30일 환산 데이터 GB]")
    print(monthly_gb.describe(
        percentiles=[0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]
    ).round(2).to_string())
    print("\n[파티션 무결성]")
    print(pd.Series({
        "연속 날짜": continuous_dates,
        "필수값 누락 행": null_rows,
        "0 이하 사용량 행": non_positive_rows,
        "파티션 내 content_usage_id 중복": duplicate_ids,
        "content_usage 복합 grain 중복": duplicate_grain,
        "존재하지 않는 user_id 참조": invalid_user_refs,
    }).to_string())
    if any([null_rows, non_positive_rows, duplicate_ids, duplicate_grain, invalid_user_refs]):
        raise ValueError("content_usage 파티션 무결성 검사에 실패했습니다")


def bundle_eligibility(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    users = tables["users"]
    plans = tables["plans"]
    families = tables["families"]
    threshold = 77000.0
    if "premium_family_discount_rules" in tables:
        high_rule = tables["premium_family_discount_rules"].loc[
            tables["premium_family_discount_rules"]["discount_id"] == "D003", "minimum_plan_fee"
        ]
        if not high_rule.empty:
            threshold = float(pd.to_numeric(high_rule.iloc[0], errors="coerce"))
    merged = users.merge(plans[["plan_id", "monthly_fee"]], left_on="current_plan_id", right_on="plan_id", how="left")
    metrics = merged.dropna(subset=["family_id"]).groupby("family_id").agg(
        mobile_lines=("user_id", "size"),
        high_lines=("monthly_fee", lambda values: int((values >= threshold).sum())),
    ).reset_index()
    return families.merge(metrics, on="family_id", how="left").fillna({"mobile_lines": 0, "high_lines": 0})


def policy_amount(rules: pd.DataFrame, discount_id: str, method: str, rule_type: str,
                  product_group: str, contract_months: int, *,
                  mobile_total: float | None = None, mobile_line_fee: float | None = None) -> float:
    candidate = rules[
        (rules["discount_id"] == discount_id)
        & (rules["bundle_discount_method"] == method)
        & (rules["rule_type"] == rule_type)
        & (pd.to_numeric(rules["contract_months"], errors="coerce") == contract_months)
        & (rules["internet_product_group"].isin([product_group, "ANY"]))
    ].copy()
    for column in ["mobile_total_fee_min", "mobile_total_fee_max", "mobile_line_fee_min", "mobile_line_fee_max", "discount_amount"]:
        candidate[column] = pd.to_numeric(candidate[column], errors="coerce")
    if mobile_total is not None:
        candidate = candidate[
            (candidate["mobile_total_fee_min"].isna() | (candidate["mobile_total_fee_min"] <= mobile_total))
            & (candidate["mobile_total_fee_max"].isna() | (mobile_total <= candidate["mobile_total_fee_max"]))
        ]
    if mobile_line_fee is not None:
        candidate = candidate[
            (candidate["mobile_line_fee_min"].isna() | (candidate["mobile_line_fee_min"] <= mobile_line_fee))
            & (candidate["mobile_line_fee_max"].isna() | (mobile_line_fee <= candidate["mobile_line_fee_max"]))
        ]
    if len(candidate) != 1:
        raise ValueError(f"정책 규칙을 하나로 해석할 수 없습니다: {discount_id}/{method}/{rule_type}")
    return float(candidate.iloc[0]["discount_amount"])


def policy_preferred_bundle_method(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """내보낸 공식 요금표로만 판단하며, 가족별 계산 결과는 CSV에 기록하지 않습니다."""
    users = tables["users"].merge(
        tables["plans"][["plan_id", "monthly_fee"]],
        left_on="current_plan_id", right_on="plan_id", how="left",
    )
    families = tables["families"]
    rules = tables["internet_bundle_discount_rules"]
    high_rule = tables["premium_family_discount_rules"].loc[
        tables["premium_family_discount_rules"]["discount_id"] == "D003"
    ].iloc[0]
    high_threshold = float(high_rule["minimum_plan_fee"])
    minimum_high_lines = int(high_rule["minimum_high_line_count"])
    records = []
    for family in families.itertuples(index=False):
        if str(family.internet_status) != "ACTIVE":
            continue
        group = family.internet_product_group if pd.notna(family.internet_product_group) else None
        if group is None or pd.isna(family.internet_contract_months):
            continue
        members = users[users["family_id"] == family.family_id].copy()
        if members.empty:
            continue
        high = members[pd.to_numeric(members["monthly_fee"], errors="coerce") >= high_threshold]
        if family.bundle_type == "PREMIUM_FAMILY":
            if len(high) < minimum_high_lines:
                continue
            base_candidates = high
        else:
            base_candidates = high if not high.empty else members
        base = base_candidates.sort_values(
            ["monthly_fee", "age", "subscription_start_date"], ascending=[True, False, True]
        ).iloc[0]
        base_and_low = (
            members[(members["user_id"] == base.user_id) | (members["monthly_fee"] < high_threshold)]
            if family.bundle_type == "PREMIUM_FAMILY" else members
        )
        term = int(float(family.internet_contract_months))
        total_fee = float(base_and_low["monthly_fee"].sum())
        total = (
            policy_amount(rules, "D001", "TOTAL", "MOBILE_TOTAL_POOL", group, term, mobile_total=total_fee)
            + policy_amount(rules, "D005", "TOTAL", "INTERNET_BASE", group, term, mobile_total=total_fee)
            + policy_amount(rules, "D005", "TOTAL", "INTERNET_ADDITIONAL", group, term)
        )
        fixed = (
            sum(policy_amount(rules, "D002", "FIXED", "MOBILE_LINE", group, term, mobile_line_fee=float(fee))
                for fee in base_and_low["monthly_fee"])
            + policy_amount(rules, "D005", "FIXED", "INTERNET_BASE", group, term)
            + policy_amount(rules, "D005", "FIXED", "INTERNET_ADDITIONAL", group, term)
        )
        records.append({
            "family_id": family.family_id,
            "policy_preferred_method": "TOTAL" if total > fixed else "FIXED",
        })
    return pd.DataFrame(records, columns=["family_id", "policy_preferred_method"])


def check_bundle_distribution(tables: dict[str, pd.DataFrame]) -> None:
    required = {"users", "families", "plans", "bundle_discount_compositions", "user_discounts", "discounts", "internet_bundle_discount_rules", "premium_family_discount_rules"}
    if not required.issubset(tables):
        return
    families = bundle_eligibility(tables)
    compositions = tables["bundle_discount_compositions"]
    entitlements = tables["user_discounts"]
    discounts = tables["discounts"]
    section("4. 인터넷-모바일 결합·프리미엄 가족결합 혜택 분포")
    value_distribution(families, "has_kt_internet")
    value_distribution(families, "internet_status")
    value_distribution(families, "internet_product_group")
    value_distribution(families, "internet_contract_months")
    value_distribution(families, "has_bundle")
    value_distribution(families, "bundle_type")
    value_distribution(families, "bundle_discount_method")
    value_distribution(families, "total_discount_allocation_method")
    high_rule = tables["premium_family_discount_rules"].loc[
        tables["premium_family_discount_rules"]["discount_id"] == "D003"
    ].iloc[0]
    eligible = families["high_lines"] >= int(high_rule["minimum_high_line_count"])
    bundled = families["has_bundle"].astype(str).str.lower().eq("true")
    active_internet = families["internet_status"].eq("ACTIVE")
    print("\n[적격·결합 시나리오 지표]")
    print(pd.Series({
        "모바일 고가 2회선 이상 적격 가족": int(eligible.sum()),
        "적격 + 활성 인터넷 + 결합 가입": int((eligible & active_internet & bundled).sum()),
        "적격 + 활성 인터넷 + 결합 미가입": int((eligible & active_internet & ~bundled).sum()),
        "적격 + 인터넷 비활성": int((eligible & ~active_internet).sum()),
        "일반 인터넷-모바일 결합 가입": int((bundled & families["bundle_type"].eq("INTERNET_MOBILE")).sum()),
        "프리미엄 가족결합 가입": int((bundled & families["bundle_type"].eq("PREMIUM_FAMILY")).sum()),
        "결합 가입 가족": int(bundled.sum()),
    }).to_string())
    method_policy = policy_preferred_bundle_method(tables)
    method_check = families.merge(method_policy, on="family_id", how="left")
    enrolled = method_check[method_check["has_bundle"].astype(str).str.lower().eq("true")]
    if not enrolled.empty:
        method_mismatch = enrolled["bundle_discount_method"].ne(enrolled["policy_preferred_method"])
        print("\n[결합 방식 선택 지표 — output 정책 구간표 기준]")
        print(pd.Series({
            "결합 가입 가족": len(enrolled),
            "정책 기준 방식 일치": int((~method_mismatch).sum()),
            "정책 기준 비최적 방식": int(method_mismatch.sum()),
            "비최적 비율": f"{method_mismatch.mean():.1%}",
        }).to_string())
    subsection("결합 구성 역할")
    value_distribution(compositions, "component_role")
    value_distribution(compositions, "component_type")
    subsection("사용자 할인 혜택")
    labelled = entitlements.merge(discounts[["discount_id", "discount_name"]], on="discount_id", how="left")
    value_distribution(labelled, "discount_name")
    per_user = entitlements.groupby("user_id").size()
    print(f"\n혜택 보유 사용자: {per_user.index.nunique():,} / {len(tables['users']):,}")
    print("사용자당 혜택 행 수:")
    print(per_user.value_counts().sort_index().to_string())
    print(f"청소년 추가 혜택(D004): {int((entitlements['discount_id'] == 'D004').sum()):,}건")


def check_integrity(tables: dict[str, pd.DataFrame]) -> None:
    required = {"users", "families", "plans", "bundle_discount_compositions", "discounts", "internet_bundle_discount_rules", "premium_family_discount_rules", "user_discounts"}
    if not required.issubset(tables):
        return
    users, families, plans = tables["users"], tables["families"], tables["plans"]
    compositions, discounts = tables["bundle_discount_compositions"], tables["discounts"]
    entitlements = tables["user_discounts"]
    internet_rules = tables["internet_bundle_discount_rules"]
    premium_rules = tables["premium_family_discount_rules"]
    section("5. output FK·구성 정합성")
    checks = {
        "users.current_plan_id → plans": users["current_plan_id"].dropna().isin(plans["plan_id"]).all(),
        "users.family_id → families": users["family_id"].dropna().isin(families["family_id"]).all(),
        "composition.family_id → families": compositions["family_id"].isin(families["family_id"]).all(),
        "mobile composition.user_id → users": compositions.loc[compositions["component_type"] == "MOBILE", "user_id"].isin(users["user_id"]).all(),
        "entitlement.user_id → users": entitlements["user_id"].isin(users["user_id"]).all(),
        "entitlement.composition → composition": entitlements["bundle_composition_id"].isin(compositions["bundle_composition_id"]).all(),
        "entitlement.discount_id → discounts": entitlements["discount_id"].isin(discounts["discount_id"]).all(),
        "internet rule.discount_id → discounts": internet_rules["discount_id"].isin(discounts["discount_id"]).all(),
        "premium rule.discount_id → discounts": premium_rules["discount_id"].isin(discounts["discount_id"]).all(),
        "families.internet_contract_months 단위": families["internet_contract_months"].dropna().isin([12, 24, 36]).all(),
        "rules.contract_months 단위": pd.to_numeric(
            internet_rules["contract_months"], errors="coerce"
        ).isin([12, 24, 36]).all(),
        "families.bundle_type 허용값": families["bundle_type"].dropna().isin(
            ["INTERNET_MOBILE", "PREMIUM_FAMILY"]
        ).all(),
        "TOTAL 배분 방식 허용값": families.loc[
            families["bundle_discount_method"] == "TOTAL", "total_discount_allocation_method"
        ].isin(["EQUAL", "CONTRIBUTION"]).all(),
    }
    if "content_usage" in tables:
        checks["content.user_id → users"] = tables["content_usage"]["user_id"].isin(users["user_id"]).all()
    print(pd.Series(checks, name="PASS").to_string())
    bundled = families[families["has_bundle"].astype(str).str.lower().eq("true")]
    if not bundled.empty:
        roles = compositions.groupby(["family_id", "component_role"]).size().unstack(fill_value=0)
        group_roles = roles.reindex(bundled["family_id"], fill_value=0)
        base_mobile = group_roles["BASE_MOBILE"] if "BASE_MOBILE" in group_roles else pd.Series(0, index=group_roles.index)
        base_internet = group_roles["BASE_INTERNET"] if "BASE_INTERNET" in group_roles else pd.Series(0, index=group_roles.index)
        print(f"\n결합 가족별 BASE_MOBILE 1개: {bool(base_mobile.eq(1).all())}")
        print(f"결합 가족별 BASE_INTERNET 1개: {bool(base_internet.eq(1).all())}")


def main() -> None:
    tables = load_tables()
    if not tables:
        print("확인할 output CSV가 없습니다. 먼저 생성기를 실행하세요.")
        return
    check_output_schema(tables)
    check_user_and_plan_distribution(tables)
    check_usage_distribution(tables)
    check_bundle_distribution(tables)
    check_integrity(tables)


if __name__ == "__main__":
    main()
