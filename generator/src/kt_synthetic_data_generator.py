#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KT 모바일 고객 합성 데이터 생성기
================================

목적
----
요금제·가족결합·초이스 혜택 추천 로직을 검증할 관계형 합성 데이터를 생성한다.
실제 개인정보는 사용하지 않는다.

마스터 데이터에 반영한 기준 정보(2026-09-15 확인)
-------------------------------------------------
1) 2026년 연령대별 인구는 통계청 장래인구추계를 사용한다. 표본 대상은 전체 거주자가
   아니라 이동통신 가입자이므로, 저연령대에는 별도 가중치 조정을 적용한다.
2) KT 통합 모바일 요금제는 음성(P10xx), 베이직 이월(P21xx), 베이직(P22xx),
   초이스(P30xx), 초이스 더블(P40xx) 계열로 분류한다.
3) 프리미엄 가족결합은 대상 KT 인터넷, 월정액 77,000원 이상 모바일 2회선 이상,
   최대 10회선 조건을 사용한다. 총액/정액 구간표, 약정기간, 고가 추가회선 25%,
   청소년 규칙은 별도 정책 마스터에 저장하며 개인별 청구 계산 결과는 출력하지 않는다.
4) 스쿨/Y/65+/75+ 덤 혜택은 연령에 따라 자동 적용되므로 기본 요금제와 분리한다.
   초이스 혜택은 plan_benefits로 정규화한다.

합성 가정은 상수·주석·마스터 데이터 컬럼에 명시한다. 이 코드는 테스트 데이터
생성용이며 실제 청구 시스템이 아니다.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import random
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from faker import Faker
except ImportError:  # pragma: no cover
    Faker = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "generated"
DEFAULT_ANALYSIS_OUTPUT_DIR = PROJECT_ROOT / "data" / "generated_analysis"
SYNTHETIC_ANALYSIS_KEY = "kt-nd-synthetic-analysis-v1"


# -----------------------------------------------------------------------------
# 0. 실행 기본값 / 재현성
# -----------------------------------------------------------------------------
N_USERS = 1000
N_DAYS = 90
SEED = 3
SUBOPTIMAL_PLAN_RATIO = 0.20
REFERENCE_DATE = pd.Timestamp("2026-09-15")

# 결합 분포는 합성 시나리오 제어값이다. 요금제·사용량 생성은 바꾸지 않으면서
# 결합 미가입 및 비최적 결합 사례를 의도적으로 만든다. 값은 프리미엄 가족결합의
# 모바일 회선 조건을 충족한 가족에만 적용한다.
INTERNET_ACTIVE_RATIO = 0.60
BUNDLE_SCENARIO_WEIGHTS = {
    "OPTIMAL_ENROLLED": 0.55,
    "SUBOPTIMAL_ENROLLED": 0.17,
    "INTERNET_ACTIVE_NOT_ENROLLED": 0.16,
    "INTERNET_INACTIVE": 0.12,
}
GENERAL_ACTIVE_BUNDLE_SCENARIO_WEIGHTS = {
    "OPTIMAL_ENROLLED": 0.62,
    "SUBOPTIMAL_ENROLLED": 0.18,
    "INTERNET_ACTIVE_NOT_ENROLLED": 0.20,
}
INTERNET_PRODUCT_GROUP_WEIGHTS = {
    "BASIC_ESSENCE_PREMIUM": 0.75,
    "SLIM": 0.25,
}

CONTENT_CATEGORIES = [
    "video",
    "short_form",
    "music",
    "ai",
    "ebook",
    "web",
    "sns",
    "messaging",
    "game",
    "video_call",
    "navigation",
    "cloud",
    "other",
]

# content_usage는 개인정보 최소화를 위한 대분류와 초이스 추천에 필요한 제한적
# 상세분류까지만 저장한다. 서비스 ID, 검색어, 제목 등은 사용량 행에 넣지 않는다.
CONTENT_DETAILS_BY_CATEGORY = {
    "video": ["netflix", "youtube_video", "tving", "disney_plus", "other_video"],
    "short_form": ["youtube_shorts", "other_short_form"],
    "music": ["youtube_music", "genie_music", "other_music"],
    "ai": ["google_ai", "other_ai"],
    "ebook": ["milli_ebook", "other_ebook"],
    "web": ["general_web"],
    "sns": ["general_sns"],
    "messaging": ["general_messaging"],
    "game": ["general_game"],
    "video_call": ["general_video_call"],
    "navigation": ["general_navigation"],
    "cloud": ["general_cloud"],
    "other": ["other"],
}

CONTENT_DETAILS = [
    detail
    for category in CONTENT_CATEGORIES
    for detail in CONTENT_DETAILS_BY_CATEGORY[category]
]

# 선택 혜택은 상세 사용량을 결정하지 않고 약한 상관만 만든다. 이 매핑은 생성기
# 내부에서만 사용하며 content_usage 출력에는 service_id를 저장하지 않는다.
SERVICE_DETAILS = {
    "S001": ["netflix"],
    "S002": ["youtube_video", "youtube_shorts", "youtube_music"],
    "S003": ["tving"],
    "S004": ["genie_music"],
    "S005": ["milli_ebook"],
    "S006": ["disney_plus"],
    "S009": ["google_ai"],
}

DETAIL_BASE_WEIGHTS = {
    "video": {
        "netflix": 0.24, "youtube_video": 0.28, "tving": 0.16,
        "disney_plus": 0.14, "other_video": 0.18,
    },
    "short_form": {"youtube_shorts": 0.65, "other_short_form": 0.35},
    "music": {"youtube_music": 0.28, "genie_music": 0.30, "other_music": 0.42},
    "ai": {"google_ai": 0.55, "other_ai": 0.45},
    "ebook": {"milli_ebook": 0.55, "other_ebook": 0.45},
}

QUOTA_CONTENT_MULTIPLIERS = {
    "NORMAL": {},
    "WATCH": {"video": 0.90, "short_form": 0.90},
    "SAVE": {"video": 0.65, "short_form": 0.70, "music": 1.05,
             "web": 1.05, "messaging": 1.05},
    "CRITICAL": {"video": 0.30, "short_form": 0.35, "music": 1.15,
                 "web": 1.10, "messaging": 1.12},
    "DEPLETED": {"video": 0.15, "short_form": 0.20, "music": 1.20,
                 "web": 1.12, "messaging": 1.15},
}

REVERSE_RELATIONSHIP = {
    "SPOUSE": "SPOUSE",
    "PARENT": "CHILD",
    "CHILD": "PARENT",
    "SIBLING": "SIBLING",
    "GRANDPARENT": "GRANDCHILD",
    "GRANDCHILD": "GRANDPARENT",
}


# -----------------------------------------------------------------------------
# 1. 외부 통계 기준값
# -----------------------------------------------------------------------------
# 통계청 2026년 장래인구추계, 단위: 천 명.
# 0~9, 10~19, 20~29, 30~39, 40~49, 50~59, 60~69, 70~79, 80+
KOREA_2026_POPULATION_THOUSANDS = {
    "0~9": 2775,
    "10~19": 4531,
    "20~29": 5888,
    "30~39": 7038,
    "40~49": 7624,
    "50~59": 8587,
    "60~69": 7980,
    "70~79": 4665,
    "80+": 2522,
}

# 합성 가정: 이동통신 가입·사용 비율은 전체 인구와 다르다.
# 어린 연령대는 의도적으로 낮추고, 나머지 연령대는 인구 분포 형태를 유지한다.
MOBILE_SUBSCRIBER_ADJUSTMENT = {
    "0~9": 0.12,
    "10~19": 0.85,
    "20~29": 1.05,
    "30~39": 1.05,
    "40~49": 1.05,
    "50~59": 1.00,
    "60~69": 0.95,
    "70~79": 0.85,
    "80+": 0.65,
}

AGE_GROUP_TO_RANGE = {
    "0~9": (8, 9),        # 대상이 휴대폰 사용자이므로, 이 최소 구현에서는 0~7세를 제외한다.
    "10~19": (10, 19),
    "20~29": (20, 29),
    "30~39": (30, 39),
    "40~49": (40, 49),
    "50~59": (50, 59),
    "60~69": (60, 69),
    "70~79": (70, 79),
    "80+": (80, 90),
}


# -----------------------------------------------------------------------------
# 2. 합성 행동 가정
# -----------------------------------------------------------------------------
PLAN_SPENDING_SCORE = {
    "학생": 0.40,
    "무직": 0.30,
    "은퇴": 0.45,
    "주부": 0.55,
    "서비스직": 0.55,
    "판매직": 0.60,
    "생산직": 0.60,
    "운송직": 0.60,
    "사무직": 0.70,
    "공무원": 0.70,
    "자영업": 0.75,
    "전문직": 0.90,
    "관리직": 1.00,
    "기타": 0.50,
}

OCCUPATION_GROUP = {
    "학생": "학생",
    "사무직": "화이트칼라",
    "전문직": "화이트칼라",
    "관리직": "화이트칼라",
    "서비스직": "서비스/판매",
    "판매직": "서비스/판매",
    "생산직": "현장/기술",
    "운송직": "현장/기술",
    "자영업": "자영업",
    "공무원": "공공",
    "주부": "비경제활동",
    "무직": "비경제활동",
    "은퇴": "비경제활동",
    "기타": "기타",
}

# 연령별 직업 확률. 한국의 노동인구 구조와 생애주기상 개연성을 느슨하게 반영한
# 합성 가정이다.
OCCUPATION_WEIGHTS_BY_AGE = {
    "0~9": {"학생": 0.98, "기타": 0.02},
    "10~19": {"학생": 0.92, "서비스직": 0.03, "판매직": 0.02, "무직": 0.02, "기타": 0.01},
    "20~29": {
        "학생": 0.18, "사무직": 0.22, "전문직": 0.13, "서비스직": 0.13,
        "판매직": 0.09, "생산직": 0.07, "운송직": 0.03, "자영업": 0.03,
        "공무원": 0.05, "무직": 0.05, "기타": 0.02,
    },
    "30~39": {
        "사무직": 0.25, "전문직": 0.16, "관리직": 0.04, "서비스직": 0.11,
        "판매직": 0.08, "생산직": 0.09, "운송직": 0.05, "자영업": 0.08,
        "공무원": 0.06, "주부": 0.04, "무직": 0.02, "기타": 0.02,
    },
    "40~49": {
        "사무직": 0.20, "전문직": 0.13, "관리직": 0.08, "서비스직": 0.12,
        "판매직": 0.08, "생산직": 0.10, "운송직": 0.06, "자영업": 0.10,
        "공무원": 0.05, "주부": 0.04, "무직": 0.02, "기타": 0.02,
    },
    "50~59": {
        "사무직": 0.13, "전문직": 0.09, "관리직": 0.08, "서비스직": 0.15,
        "판매직": 0.09, "생산직": 0.12, "운송직": 0.08, "자영업": 0.12,
        "공무원": 0.04, "주부": 0.04, "무직": 0.02, "은퇴": 0.02, "기타": 0.02,
    },
    "60~69": {
        "사무직": 0.05, "전문직": 0.04, "관리직": 0.03, "서비스직": 0.15,
        "판매직": 0.08, "생산직": 0.08, "운송직": 0.08, "자영업": 0.14,
        "공무원": 0.01, "주부": 0.07, "무직": 0.05, "은퇴": 0.19, "기타": 0.03,
    },
    "70~79": {
        "서비스직": 0.08, "판매직": 0.04, "생산직": 0.03, "운송직": 0.03,
        "자영업": 0.07, "주부": 0.10, "무직": 0.07, "은퇴": 0.54, "기타": 0.04,
    },
    "80+": {"자영업": 0.02, "주부": 0.08, "무직": 0.07, "은퇴": 0.79, "기타": 0.04},
}

USAGE_PROFILE_DAILY_MB = {
        # 합성 잠재 프로필. 저용량·음성 요금제가 의도적 이상치로만 나타나지 않도록
        # VERY_LOW 구간을 포함한다.
    "VERY_LOW": 25.0,    # 월 약 0.7GB
    "LOW": 180.0,        # 월 약 5.3GB
    "MEDIUM": 700.0,     # 월 약 20.5GB
    "HIGH": 2000.0,      # 월 약 58.6GB
    "VERY_HIGH": 4200.0, # 월 약 123GB
}


# -----------------------------------------------------------------------------
# 3. 마스터 데이터
# -----------------------------------------------------------------------------
def create_plan_master() -> pd.DataFrame:
    """현재 KT 모바일 요금제 중심의 마스터를 생성한다.

    요금제 ID 체계
    ------------
    P10xx : 음성 중심 통합 요금제
    P21xx : 베이직 이월 계열
    P22xx : 베이직 계열
    P30xx : 초이스 계열
    P40xx : 초이스 더블 계열

    향후 계열을 추가해도 기존 마스터의 번호를 바꾸지 않도록 앞 두 자리를
    상품 계열별로 분리했다.
    """
    rows = [
        # plan_id, plan_name, 계열, 카테고리, 월정액, 데이터GB, 무제한, 소진후속도,
        # 음성, 문자, 공유데이터GB, 이월, 멤버십, 초이스 여부, 초이스 등급,
        # 기기 할인 회선수, 데이터쉐어링 할인 회선수, 가족결합 가능, 가격대, 기준정보
        ("P1001", "음성18.7", "VOICE", "통합 음성", 18700, 0.0, False, None,
         "100분", "100건", 0.0, False, None, False, None, 0, 0, True, "저가", "KT official"),

        # 베이직 이월: 남은 기본 데이터를 다음 달로 이월한다.
        ("P2101", "베이직4GB(이월)", "BASIC_ROLLOVER", "베이직(이월)", 37000, 4.0, False, None,
         "기본제공", "기본제공", 4.0, True, None, False, None, 0, 0, True, "저가", "KT official"),
        ("P2102", "베이직7GB(이월)", "BASIC_ROLLOVER", "베이직(이월)", 45000, 7.0, False, None,
         "기본제공", "기본제공", 7.0, True, None, False, None, 0, 0, True, "중저가", "KT official"),
        ("P2103", "베이직10GB(이월)", "BASIC_ROLLOVER", "베이직(이월)", 50000, 10.0, False, None,
         "기본제공", "기본제공", 10.0, True, None, False, None, 0, 0, True, "중저가", "KT official"),
        ("P2104", "베이직14GB(이월)", "BASIC_ROLLOVER", "베이직(이월)", 55000, 14.0, False, None,
         "기본제공", "기본제공", 14.0, True, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2105", "베이직21GB(이월)", "BASIC_ROLLOVER", "베이직(이월)", 58000, 21.0, False, None,
         "기본제공", "기본제공", 21.0, True, None, False, None, 0, 0, True, "중가", "KT official"),

        # 베이직 계열.
        ("P2201", "베이직600MB", "BASIC", "베이직", 28900, 0.6, False, "400Kbps",
         "180분", "180건", 0.6, False, None, False, None, 0, 0, True, "저가", "KT official"),
        ("P2202", "베이직1.4GB", "BASIC", "베이직", 33000, 1.4, False, "400Kbps",
         "기본제공", "기본제공", 1.4, False, None, False, None, 0, 0, True, "저가", "KT official"),
        ("P2203", "베이직4GB", "BASIC", "베이직", 37000, 4.0, False, "400Kbps",
         "기본제공", "기본제공", 4.0, False, None, False, None, 0, 0, True, "저가", "KT official"),
        ("P2204", "베이직7GB", "BASIC", "베이직", 45000, 7.0, False, "400Kbps",
         "기본제공", "기본제공", 7.0, False, None, False, None, 0, 0, True, "중저가", "KT official"),
        ("P2205", "베이직10GB", "BASIC", "베이직", 50000, 10.0, False, "400Kbps",
         "기본제공", "기본제공", 10.0, False, None, False, None, 0, 0, True, "중저가", "KT official"),
        ("P2206", "베이직14GB", "BASIC", "베이직", 55000, 14.0, False, "1Mbps",
         "기본제공", "기본제공", 14.0, False, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2207", "베이직21GB", "BASIC", "베이직", 58000, 21.0, False, "1Mbps",
         "기본제공", "기본제공", 21.0, False, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2208", "베이직30GB", "BASIC", "베이직", 61000, 30.0, False, "1Mbps",
         "기본제공", "기본제공", 30.0, False, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2209", "베이직50GB", "BASIC", "베이직", 63000, 50.0, False, "1Mbps",
         "기본제공", "기본제공", 50.0, False, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2210", "베이직70GB", "BASIC", "베이직", 65000, 70.0, False, "1Mbps",
         "기본제공", "기본제공", 70.0, False, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2211", "베이직90GB", "BASIC", "베이직", 67000, 90.0, False, "1Mbps",
         "기본제공", "기본제공", 90.0, False, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2212", "베이직110GB", "BASIC", "베이직", 69000, 110.0, False, "5Mbps",
         "기본제공", "기본제공", 110.0, False, None, False, None, 0, 0, True, "중가", "KT official"),
        ("P2213", "베이직80", "BASIC", "베이직", 80000, np.nan, True, None,
         "기본제공", "기본제공", 50.0, False, "VIP", False, None, 0, 0, True, "고가", "KT official"),
        ("P2214", "베이직100", "BASIC", "베이직", 100000, np.nan, True, None,
         "기본제공", "기본제공", 70.0, False, "VVIP", False, None, 1, 1, True, "고가", "KT official"),

        # 초이스 계열. 공유 데이터 한도는 휴대폰 데이터 무제한과 별개다.
        ("P3001", "초이스90", "CHOICE", "초이스", 90000, np.nan, True, None,
         "기본제공", "기본제공", 60.0, False, "VIP", True, "BASIC", 0, 1, True, "고가", "KT official"),
        ("P3002", "초이스110", "CHOICE", "초이스", 110000, np.nan, True, None,
         "기본제공", "기본제공", 80.0, False, "VVIP", True, "SPECIAL", 1, 1, True, "프리미엄", "KT official"),
        ("P3003", "초이스130", "CHOICE", "초이스", 130000, np.nan, True, None,
         "기본제공", "기본제공", 100.0, False, "VVIP", True, "PREMIUM", 2, 1, True, "프리미엄", "KT official"),

        # 초이스 더블: 일반화한 12만원 구간이며, 선택한 더블 혜택 패키지는 별도로 저장한다.
        ("P4001", "초이스 더블", "CHOICE_DOUBLE", "초이스 더블", 120000, np.nan, True, None,
         "기본제공", "기본제공", 90.0, False, "VVIP", True, "DOUBLE", 1, 1, True, "프리미엄", "KT official"),
    ]
    columns = [
        "plan_id", "plan_name", "plan_family", "plan_category", "monthly_fee",
        "data_limit_gb", "is_unlimited", "throttle_speed", "voice", "sms",
        "base_shared_data_gb", "is_rollover", "membership_tier",
        "is_choice_plan", "choice_tier", "device_discount_lines",
        "data_sharing_discount_lines", "family_bundle_eligible", "price_band", "source_status",
    ]
    df = pd.DataFrame(rows, columns=columns)
    # 기준 요금제 목록에는 과거·현재 상품 계열이 함께 있다. 프리미엄 가족결합 청소년
    # 혜택 판정을 위해 망 유형을 명시하며, 이 합성 모델에서는 현재 8만원 이상 5G
    # 구간만 청소년 혜택 대상으로 둔다.
    youth_5g_plan_ids = {"P2213", "P2214", "P3001", "P3002", "P3003", "P4001"}
    df["network_type"] = np.where(df["plan_id"].isin(youth_5g_plan_ids), "5G", "LTE_OR_5G")
    df["target_age_min"] = np.nan
    df["target_age_max"] = np.nan
    df["description"] = df.apply(
        lambda r: f"{r['plan_category']} / {r['price_band']} / {r['source_status']}", axis=1
    )
    return df


def create_age_benefit_master() -> pd.DataFrame:
    """연령별 덤 혜택 정의. plan_age_benefits에 행이 있는 경우에만 적용한다."""
    rows = [
        ("AB10", "스쿨덤", 8, 18, True, "청소년 데이터 최대 2배 + 안심박스"),
        ("AB20", "Y덤", 19, 34, False, "청년 데이터 2배"),
        ("AB30", "65+덤", 65, 74, True, "시니어 데이터 최대 1.5배 + 안심박스"),
        ("AB40", "75+덤", 75, None, True, "시니어 데이터 최대 2배 + 안심박스"),
    ]
    return pd.DataFrame(rows, columns=[
        "age_benefit_id", "benefit_name", "min_age", "max_age", "includes_safety_box", "description"
    ])


def create_plan_age_benefits(plans: pd.DataFrame) -> pd.DataFrame:
    """KT 현재 통합 요금제 혜택표 기반의 요금제 × 연령 덤 마스터.

    `bonus_data_gb`는 유한 데이터 베이직·이월 요금제의 휴대폰 기본 데이터를 늘린다.
    `bonus_shared_data_gb`는 무제한 베이직·초이스·초이스 더블의 스마트기기/공유
    데이터만 늘리므로, 추천 적합도에 쓰는 휴대폰 데이터 한도에는 더하지 않는다.
    """
    pid = plans.set_index("plan_name")["plan_id"].to_dict()
    rows: List[dict] = []
    seq = 1

    def add(plan_name: str, benefit_id: str, *, bonus_data: float = 0.0,
            bonus_shared: float = 0.0, bonus_voice: float = 0.0,
            bonus_sms: float = 0.0, bonus_video: float = 0.0,
            note: str = "") -> None:
        nonlocal seq
        if plan_name not in pid:
            return
        rows.append({
            "plan_age_benefit_id": f"PAB{seq:04d}",
            "plan_id": pid[plan_name],
            "age_benefit_id": benefit_id,
            "bonus_data_gb": float(bonus_data),
            "bonus_shared_data_gb": float(bonus_shared),
            "bonus_voice_minutes": float(bonus_voice),
            "bonus_sms_count": float(bonus_sms),
            "bonus_video_minutes": float(bonus_video),
            "note": note,
            "source_status": "KT official age-bonus table",
        })
        seq += 1

    finite_basic = {
        "베이직1.4GB": 1.4, "베이직4GB": 4, "베이직7GB": 7, "베이직10GB": 10,
        "베이직14GB": 14, "베이직21GB": 21, "베이직30GB": 30, "베이직50GB": 50,
        "베이직70GB": 70, "베이직90GB": 90, "베이직110GB": 110,
        "베이직4GB(이월)": 4, "베이직7GB(이월)": 7, "베이직10GB(이월)": 10,
        "베이직14GB(이월)": 14, "베이직21GB(이월)": 21,
    }

    # 스쿨덤과 75+덤은 일반적으로 유한 기본 데이터를 두 배로 만든다.
    for name, amount in finite_basic.items():
        add(name, "AB10", bonus_data=amount)
        add(name, "AB40", bonus_data=amount, bonus_video=(50 if name == "베이직1.4GB" else 0))

    # Y덤은 베이직 1.4GB 이상 및 이월 4GB 이상에 적용하며, 600MB·음성은 대상이 아니다.
    for name, amount in finite_basic.items():
        add(name, "AB20", bonus_data=amount)

    # 65+덤은 KT의 현재 반올림된 약 50% 추가 제공량을 사용한다.
    senior65 = {
        "베이직1.4GB": 0.7, "베이직4GB": 2, "베이직7GB": 4, "베이직10GB": 5,
        "베이직14GB": 7, "베이직21GB": 11, "베이직30GB": 15, "베이직50GB": 25,
        "베이직70GB": 35, "베이직90GB": 45, "베이직110GB": 55,
        "베이직4GB(이월)": 2, "베이직7GB(이월)": 4, "베이직10GB(이월)": 5,
        "베이직14GB(이월)": 7, "베이직21GB(이월)": 11,
    }
    for name, amount in senior65.items():
        add(name, "AB30", bonus_data=amount, bonus_video=(50 if name == "베이직1.4GB" else 0))

    # 특수 저가 구간.
    add("음성18.7", "AB10", bonus_data=0.6, note="스쿨덤: 데이터 600MB")
    add("음성18.7", "AB30", bonus_data=0.3, bonus_voice=30, bonus_sms=50,
        note="65+덤: 데이터 300MB + 음성/문자 추가")
    add("음성18.7", "AB40", bonus_data=0.3, bonus_voice=30, bonus_sms=50,
        note="75+덤: 데이터 300MB + 음성/문자 추가")
    add("베이직600MB", "AB10", bonus_data=0.4, note="총 1,000MB")
    add("베이직600MB", "AB30", bonus_data=0.2, bonus_video=100,
        note="총 800MB; 음성/문자/영상 혜택 별도")
    add("베이직600MB", "AB40", bonus_data=0.4, bonus_video=100,
        note="총 1,000MB; 음성/문자/영상 혜택 별도")

    # 무제한 구간: 연령 혜택은 휴대폰 무제한 데이터가 아니라 공유 데이터를 늘린다.
    shared = {
        "베이직80": 50, "베이직100": 70,
        "초이스90": 60, "초이스110": 80, "초이스130": 100,
        "초이스 더블": 90,
    }
    for name, base_shared in shared.items():
        add(name, "AB10", bonus_shared=base_shared)
        add(name, "AB20", bonus_shared=base_shared)
        add(name, "AB30", bonus_shared=base_shared / 2.0)
        add(name, "AB40", bonus_shared=base_shared)

    return pd.DataFrame(rows)


def create_service_master() -> pd.DataFrame:
    """추천 테스트용 부가서비스 목록.

    초이스 더블은 합성 패키지 행이 아니라 개별 서비스로 표현한다. 따라서 사용자가
    선택한 두 혜택을 user_services의 두 행으로 저장할 수 있다.
    """
    rows = [
        ("S001", "Netflix 스탠다드", "video", 13500, "KT Choice max discount value", "넷플릭스 스탠다드"),
        ("S002", "YouTube Premium Lite", "video_music", 10000, "synthetic_reference_value", "유튜브 프리미엄 라이트"),
        ("S003", "티빙 스탠다드", "video", 13500, "synthetic_reference_value", "티빙 스탠다드"),
        ("S004", "지니뮤직", "music", 10600, "KT related service reference", "지니 음악 서비스"),
        ("S005", "밀리의서재", "ebook", 9900, "synthetic_reference_value", "전자책 구독"),
        ("S006", "Disney+ 스탠다드", "video", 9900, "KT Choice max discount/reference", "디즈니+ 스탠다드"),
        ("S007", "스마트기기/데이터쉐어링 할인", "device", 11000, "KT benefit reference", "회선 할인 가치"),
        ("S008", "단말보험 멤버십 할인", "device_insurance", 4500, "KT official max membership discount", "월 최대 4,500원"),
        ("S009", "Google AI Plus(400GB)", "ai", 0, "benefit_only_no_price", "초이스 더블 제공 옵션"),
    ]
    return pd.DataFrame(rows, columns=[
        "service_id", "service_name", "service_category", "normal_monthly_price",
        "price_source_status", "description",
    ])


def create_plan_benefits(plans: pd.DataFrame, services: pd.DataFrame) -> pd.DataFrame:
    rows: List[dict] = []
    seq = 1

    def add(plan_id: str, service_id: str, benefit_type: str, benefit_value: str,
            selectable: bool, option_group: str = "", selection_count: int = 0) -> None:
        nonlocal seq
        rows.append({
            "plan_benefit_id": f"PB{seq:04d}",
            "plan_id": plan_id,
            "service_id": service_id,
            "benefit_type": benefit_type,
            "benefit_value": benefit_value,
            "is_selectable": bool(selectable),
            "option_group": option_group,
            "selection_count": int(selection_count),
        })
        seq += 1

    primary_services = ["S001", "S002", "S003", "S004", "S005", "S006"]
    for pid_ in ["P3001", "P3002", "P3003"]:
        for sid in primary_services:
            add(pid_, sid, "CHOICE", "택1", True, "PRIMARY_CHOICE", 1)

    # 추천용 정규화에서는 110/130 구간에 플러스 혜택 하나를 추가로 제공한다.
    for pid_ in ["P3002", "P3003"]:
        for sid in ["S004", "S005"]:
            add(pid_, sid, "PLUS", "택1", True, "PLUS_CHOICE", 1)

    # 초이스 더블은 개별 선택 서비스 두 개로 정규화한다.
    # 후보 풀은 이전에 패키지 행으로 표현했던 구성요소를 따른다.
    for sid in ["S001", "S002", "S006", "S007", "S008", "S009"]:
        add("P4001", sid, "DOUBLE_CHOICE", "택2", True, "DOUBLE_CHOICE", 2)

    # 더블이 아닌 구간의 고정 기기·보험 혜택은 별도 행으로 표현한다.
    add("P3002", "S007", "DEVICE", "스마트기기 1회선 할인", False)
    add("P3003", "S007", "DEVICE", "스마트기기 2회선 할인", False)
    add("P3002", "S008", "INSURANCE", "멤버십 할인 최대", False)
    add("P3003", "S008", "INSURANCE", "멤버십 할인 최대", False)
    add("P2214", "S007", "DEVICE", "스마트기기 또는 데이터쉐어링 1회선", False)

    return pd.DataFrame(rows)


def create_discount_master() -> pd.DataFrame:
    """사용자·가족 적용 혜택이 참조하는 공통 식별자.

    금액과 자격 구간은 아래 정책 계열 테이블에만 둔다. 이렇게 하면
    ``user_discounts``의 참조를 안정적으로 유지하면서 정책 테이블별 다형 참조를 피할 수 있다.
    """
    rows = [
        ("D001", "INTERNET_BUNDLE", "TOTAL_MOBILE_POOL", "총액결합 모바일 풀 혜택"),
        ("D002", "INTERNET_BUNDLE", "FIXED_MOBILE_LINE", "정액결합 모바일 회선 혜택"),
        ("D003", "PREMIUM_FAMILY", "ADDITIONAL_HIGH_25PCT", "프리미엄 가족결합 고가 추가 회선 혜택"),
        ("D004", "PREMIUM_FAMILY", "YOUTH_5G", "프리미엄 가족결합 청소년 혜택"),
        ("D005", "INTERNET_BUNDLE", "INTERNET_COMPONENT", "인터넷 결합 혜택"),
    ]
    return pd.DataFrame(rows, columns=[
        "discount_id", "policy_domain", "benefit_code", "discount_name",
    ])


def create_internet_bundle_discount_rules() -> pd.DataFrame:
    """현재 KT 총액/정액 인터넷-모바일 결합 할인 구간표.

    금액은 부가세 포함 정책값이며 생성된 개인 청구 결과가 아니다. 1/2/3년 약정은
    KT가 공개한 1/4·1/2·전액 기준으로 산출한다. 현재 생성하는 인터넷 구간은
    BASIC/ESSENCE/PREMIUM으로 제한하지만, 정책 마스터에는 이후 상품 확장을 위해
    공개된 다른 구간도 보존한다.
    """
    rows: List[dict] = []
    seq = 1

    def add(discount_id: str, method: str, rule_type: str, product_group: str,
            months: int, target: str, amount: float, *, total_min: float = np.nan,
            total_max: float = np.nan, line_min: float = np.nan,
            line_max: float = np.nan, allocation: str = "NOT_APPLICABLE") -> None:
        nonlocal seq
        rows.append({
            "internet_bundle_rule_id": f"IBR{seq:04d}",
            "discount_id": discount_id,
            "bundle_discount_method": method,
            "rule_type": rule_type,
            "internet_product_group": product_group,
            "contract_months": months,
            "mobile_total_fee_min": total_min,
            "mobile_total_fee_max": total_max,
            "mobile_line_fee_min": line_min,
            "mobile_line_fee_max": line_max,
            "discount_target": target,
            "allocation_method": allocation,
            "discount_amount": float(amount),
            "discount_rate": np.nan,
            "effective_start_date": None,
            "effective_end_date": None,
        })
        seq += 1

    contract_scale = {12: 0.25, 24: 0.50, 36: 1.00}
    total_cards = {
        "BASIC_ESSENCE_PREMIUM": {
            "combined": [2200, 5500, 11000, 22110, 27610, 33110],
            "internet": [2200, 5500, 5500, 5500, 5500, 5500],
        },
        "SLIM": {
            "combined": [1650, 3300, 8800, 19800, 24200, 28600],
            "internet": [1650, 3300, 5500, 5500, 5500, 5500],
        },
    }
    total_ranges = [(0, 21999), (22000, 64899), (64900, 108899),
                    (108900, 141899), (141900, 174899), (174900, np.nan)]
    for group, card in total_cards.items():
        for months, scale in contract_scale.items():
            for (minimum, maximum), combined, internet in zip(total_ranges, card["combined"], card["internet"]):
                mobile = combined - internet
                add("D001", "TOTAL", "MOBILE_TOTAL_POOL", group, months, "MOBILE_POOL",
                    mobile * scale, total_min=minimum, total_max=maximum,
                    allocation="EQUAL_OR_CONTRIBUTION")
                add("D005", "TOTAL", "INTERNET_BASE", group, months, "BASE_INTERNET",
                    internet * scale, total_min=minimum, total_max=maximum,
                    allocation="BASE_MOBILE_OR_INTERNET_SPLIT")

    # KT는 이를 모바일 총액 구간표와 별도의 추가 인터넷 할인으로 공개한다.
    # 인터넷과 모바일을 결합했을 때 적용한다.
    for method in ("TOTAL", "FIXED"):
        for months, scale in contract_scale.items():
            for group, amount in {
                "BASIC_ESSENCE_PREMIUM": 5500,
                "SLIM": 0,
            }.items():
                add("D005", method, "INTERNET_ADDITIONAL", group, months,
                    "INTERNET_ADDITIONAL", amount * scale)

    fixed_ranges = [(0, 36999, 0), (37000, 60999, 3000),
                    (61000, 76999, 5000), (77000, np.nan, 7000)]
    for months, scale in contract_scale.items():
        for minimum, maximum, amount in fixed_ranges:
            add("D002", "FIXED", "MOBILE_LINE", "ANY", months, "MOBILE_LINE",
                amount * scale, line_min=minimum, line_max=maximum)
        add("D005", "FIXED", "INTERNET_BASE", "ANY", months, "BASE_INTERNET", 5500 * scale,
            allocation="BASE_MOBILE_OR_INTERNET_SPLIT")

    return pd.DataFrame(rows)


def create_premium_family_discount_rules() -> pd.DataFrame:
    """현재 프리미엄 가족결합 자격 및 혜택 정책 규칙.

    25%는 프리미엄 가족결합 혜택 자체의 비율이다. 선택약정 할인과 사용자별
    실제 할인금액 또는 최종 청구금액은 이 모델에서 계산하거나 저장하지 않는다.
    """
    rows = [
        {
            "premium_family_rule_id": "PFR001",
            "discount_id": "D003",
            "benefit_type": "ADDITIONAL_HIGH_25PCT",
            "eligible_component_role": "PREMIUM_MOBILE",
            "requires_internet": True,
            "minimum_high_line_count": 2,
            "maximum_mobile_line_count": 10,
            "minimum_plan_fee": 77000.0,
            "required_network_type": "ANY",
            "guardian_minimum_plan_fee": np.nan,
            "guardian_required_network_type": "ANY",
            "enrollment_min_age": np.nan,
            "enrollment_max_age": np.nan,
            "benefit_end_age": np.nan,
            "requires_legal_guardian": False,
            "discount_rate": 0.25,
            "discount_amount": np.nan,
            "effective_start_date": None,
            "effective_end_date": None,
        },
        {
            "premium_family_rule_id": "PFR002",
            "discount_id": "D004",
            "benefit_type": "YOUTH_5G",
            "eligible_component_role": "HIGH_MOBILE",
            "requires_internet": True,
            "minimum_high_line_count": 2,
            "maximum_mobile_line_count": 10,
            "minimum_plan_fee": 80000.0,
            "required_network_type": "5G",
            "guardian_minimum_plan_fee": 80000.0,
            "guardian_required_network_type": "5G",
            "enrollment_min_age": 0.0,
            "enrollment_max_age": 18.0,
            "benefit_end_age": 20.0,
            "requires_legal_guardian": True,
            "discount_rate": np.nan,
            "discount_amount": 5500.0,
            "effective_start_date": None,
            "effective_end_date": None,
        },
    ]
    return pd.DataFrame(rows)


def load_reference_data() -> Dict[str, object]:
    return {
        "population_2026_thousands": KOREA_2026_POPULATION_THOUSANDS,
        "mobile_subscriber_adjustment": MOBILE_SUBSCRIBER_ADJUSTMENT,
        "occupation_weights_by_age": OCCUPATION_WEIGHTS_BY_AGE,
        "plan_spending_score": PLAN_SPENDING_SCORE,
    }


# -----------------------------------------------------------------------------
# 4. 공통 보조 함수
# -----------------------------------------------------------------------------
def normalize_weights(d: Dict[str, float]) -> Tuple[List[str], np.ndarray]:
    keys = list(d.keys())
    values = np.asarray([d[k] for k in keys], dtype=float)
    if (values < 0).any() or values.sum() <= 0:
        raise ValueError("weights must be non-negative and sum to > 0")
    return keys, values / values.sum()


def weighted_choice(rng: np.random.Generator, weights: Dict[str, float]) -> str:
    keys, probs = normalize_weights(weights)
    return str(rng.choice(keys, p=probs))


def age_group_from_age(age: int) -> str:
    if age <= 9:
        return "0~9"
    if age <= 19:
        return "10~19"
    if age <= 29:
        return "20~29"
    if age <= 39:
        return "30~39"
    if age <= 49:
        return "40~49"
    if age <= 59:
        return "50~59"
    if age <= 69:
        return "60~69"
    if age <= 79:
        return "70~79"
    return "80+"


def mobile_age_group_probs() -> Tuple[List[str], np.ndarray]:
    weighted = {
        g: KOREA_2026_POPULATION_THOUSANDS[g] * MOBILE_SUBSCRIBER_ADJUSTMENT[g]
        for g in KOREA_2026_POPULATION_THOUSANDS
    }
    return normalize_weights(weighted)


def sample_independent_age(rng: np.random.Generator) -> int:
    groups, probs = mobile_age_group_probs()
    group = str(rng.choice(groups, p=probs))
    lo, hi = AGE_GROUP_TO_RANGE[group]
    return int(rng.integers(lo, hi + 1))


def make_name_generator(seed: int):
    if Faker is not None:
        fake = Faker("ko_KR")
        fake.seed_instance(seed)
        return lambda: fake.name()

    surnames = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"]
    given1 = ["민", "서", "지", "현", "도", "예", "수", "하", "준", "유"]
    given2 = ["준", "연", "우", "민", "진", "윤", "원", "서", "영", "호"]
    py_rng = random.Random(seed)
    return lambda: py_rng.choice(surnames) + py_rng.choice(given1) + py_rng.choice(given2)


def safe_softmax(scores: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scores = np.asarray(scores, dtype=float) / max(temperature, 1e-6)
    scores = scores - np.max(scores)
    probs = np.exp(scores)
    if not np.isfinite(probs).all() or probs.sum() <= 0:
        return np.ones(len(scores)) / len(scores)
    return probs / probs.sum()


# -----------------------------------------------------------------------------
# 5. 가족 구조 / 사용자
# -----------------------------------------------------------------------------
FAMILY_TYPE_WEIGHTS = {
    "NUCLEAR_3": 0.08,
    "NUCLEAR_4": 0.08,
    "SINGLE_PARENT_2": 0.04,
    "COUPLE_2": 0.26,
    "THREE_GENERATION_3": 0.04,
    "SIBLINGS_2": 0.18,
    "ADULT_PARENT_CHILD_2": 0.26,
    "EXTENDED_5": 0.06,
}

FAMILY_TYPE_SIZE = {
    "NUCLEAR_3": 3,
    "NUCLEAR_4": 4,
    "SINGLE_PARENT_2": 2,
    "COUPLE_2": 2,
    "THREE_GENERATION_3": 3,
    "SIBLINGS_2": 2,
    "ADULT_PARENT_CHILD_2": 2,
    "EXTENDED_5": 5,
}


def generate_family_structures(n_users: int, rng: np.random.Generator,
                               family_user_ratio: float = 0.56) -> pd.DataFrame:
    target = max(0, min(n_users, int(round(n_users * family_user_ratio))))
    # 남은 인원이 1명이 되어 가족을 구성할 수 없는 경우 한 단계 낮춘다.
    if target == 1:
        target = 0

    families = []
    used = 0
    seq = 1
    while used + 2 <= target:
        remaining = target - used
        candidates = {k: w for k, w in FAMILY_TYPE_WEIGHTS.items() if FAMILY_TYPE_SIZE[k] <= remaining}
        if not candidates:
            break
        ftype = weighted_choice(rng, candidates)
        fsize = FAMILY_TYPE_SIZE[ftype]
        families.append({
            "family_id": f"F{seq:04d}",
            "family_type": ftype,
            "family_size": fsize,
            "kt_customer_count": fsize,
            "has_bundle": False,
            "bundle_type": None,
            "created_at": REFERENCE_DATE.date().isoformat(),
        })
        used += fsize
        seq += 1

    return pd.DataFrame(families)


def sample_adult_age_from_population(rng: np.random.Generator, min_age: int = 20, max_age: int = 84) -> int:
    groups, probs = mobile_age_group_probs()
    pairs = [(g, p) for g, p in zip(groups, probs) if AGE_GROUP_TO_RANGE[g][1] >= min_age and AGE_GROUP_TO_RANGE[g][0] <= max_age]
    gs = [g for g, _ in pairs]
    ps = np.array([p for _, p in pairs], dtype=float)
    ps /= ps.sum()
    g = str(rng.choice(gs, p=ps))
    lo, hi = AGE_GROUP_TO_RANGE[g]
    lo, hi = max(lo, min_age), min(hi, max_age)
    return int(rng.integers(lo, hi + 1))


def generate_family_ages(ftype: str, rng: np.random.Generator) -> Dict[str, int]:
    """논리적으로 일관된 연령을 생성한다. 모든 연령 차이는 합성 검증 규칙이다."""
    if ftype == "NUCLEAR_3":
        p1 = int(rng.integers(32, 58))
        p2 = int(np.clip(p1 + rng.integers(-6, 7), 28, 62))
        max_child = max(8, min(29, min(p1, p2) - 18))
        child = int(rng.integers(8, max_child + 1))
        return {"parent1": p1, "parent2": p2, "child1": child}

    if ftype == "NUCLEAR_4":
        p1 = int(rng.integers(34, 60))
        p2 = int(np.clip(p1 + rng.integers(-6, 7), 29, 63))
        max_child = max(10, min(30, min(p1, p2) - 18))
        c1 = int(rng.integers(8, max_child + 1))
        c2 = int(np.clip(c1 + rng.integers(-5, 6), 8, max_child))
        return {"parent1": p1, "parent2": p2, "child1": c1, "child2": c2}

    if ftype == "SINGLE_PARENT_2":
        p = int(rng.integers(30, 61))
        max_child = max(8, min(30, p - 18))
        c = int(rng.integers(8, max_child + 1))
        return {"parent1": p, "child1": c}

    if ftype == "COUPLE_2":
        a = sample_adult_age_from_population(rng, 22, 80)
        b = int(np.clip(a + rng.integers(-8, 9), 20, 84))
        return {"spouse1": a, "spouse2": b}

    if ftype == "THREE_GENERATION_3":
        gp = int(rng.integers(63, 86))
        p_hi = max(36, min(62, gp - 18))
        p = int(rng.integers(36, p_hi + 1))
        c_hi = max(8, min(29, p - 18))
        c = int(rng.integers(8, c_hi + 1))
        return {"grandparent": gp, "parent1": p, "child1": c}

    if ftype == "SIBLINGS_2":
        a = sample_adult_age_from_population(rng, 18, 75)
        b = int(np.clip(a + rng.integers(-8, 9), 10, 82))
        return {"sibling1": a, "sibling2": b}

    if ftype == "ADULT_PARENT_CHILD_2":
        p = int(rng.integers(55, 86))
        child_hi = max(25, min(60, p - 18))
        c = int(rng.integers(25, child_hi + 1))
        return {"parent1": p, "adult_child1": c}

    if ftype == "EXTENDED_5":
        gp = int(rng.integers(64, 84))
        p1_hi = max(38, min(60, gp - 18))
        p1 = int(rng.integers(38, p1_hi + 1))
        p2 = int(np.clip(p1 + rng.integers(-6, 7), 33, min(64, gp - 18)))
        c_hi = max(9, min(28, min(p1, p2) - 18))
        c1 = int(rng.integers(8, c_hi + 1))
        c2 = int(np.clip(c1 + rng.integers(-5, 6), 8, c_hi))
        return {"grandparent": gp, "parent1": p1, "parent2": p2, "child1": c1, "child2": c2}

    raise ValueError(f"Unknown family type: {ftype}")


def gender_for_role(role: str, rng: np.random.Generator) -> str:
    # 합성 데이터이며 실제의 모든 가족 구조를 표현하려는 것은 아니다.
    if role in {"parent1", "spouse1"}:
        return str(rng.choice(["M", "F"]))
    if role in {"parent2", "spouse2"}:
        return str(rng.choice(["M", "F"]))
    return str(rng.choice(["M", "F"]))


def generate_family_members(families: pd.DataFrame, seed: int,
                            start_user_seq: int = 1) -> Tuple[pd.DataFrame, Dict[str, Dict[str, str]]]:
    rng = np.random.default_rng(seed)
    name_fn = make_name_generator(seed)
    users = []
    role_map: Dict[str, Dict[str, str]] = {}
    seq = start_user_seq

    for fam in families.itertuples(index=False):
        ages = generate_family_ages(fam.family_type, rng)
        role_map[fam.family_id] = {}
        for role, age in ages.items():
            uid = f"U{seq:05d}"
            role_map[fam.family_id][role] = uid
            users.append({
                "user_id": uid,
                "name": name_fn(),
                "age": int(age),
                "age_group": age_group_from_age(int(age)),
                "gender": gender_for_role(role, rng),
                "family_id": fam.family_id,
                "family_role": role,
                "has_family": True,
            })
            seq += 1

    return pd.DataFrame(users), role_map


def generate_independent_users(count: int, seed: int, start_user_seq: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    name_fn = make_name_generator(seed)
    users = []
    for i in range(count):
        age = sample_independent_age(rng)
        users.append({
            "user_id": f"U{start_user_seq + i:05d}",
            "name": name_fn(),
            "age": age,
            "age_group": age_group_from_age(age),
            "gender": str(rng.choice(["M", "F"])),
            "family_id": None,
            "family_role": "INDEPENDENT",
            "has_family": False,
        })
    return pd.DataFrame(users)


def generate_family_relationships(role_map: Dict[str, Dict[str, str]]) -> pd.DataFrame:
    rows: List[dict] = []
    seq = 1

    def add(fid: str, a: str, b: str, relation: str) -> None:
        nonlocal seq
        if not a or not b or a == b:
            return
        rows.append({
            "relationship_id": f"R{seq:05d}",
            "family_id": fid,
            "user_id": a,
            "related_user_id": b,
            "relationship_type": relation,
        })
        seq += 1

    for fid, r in role_map.items():
        if "parent1" in r and "parent2" in r:
            add(fid, r["parent1"], r["parent2"], "SPOUSE")
        if "spouse1" in r and "spouse2" in r:
            add(fid, r["spouse1"], r["spouse2"], "SPOUSE")

        children = [r[k] for k in ("child1", "child2") if k in r]
        adult_children = [r[k] for k in ("adult_child1",) if k in r]
        parents = [r[k] for k in ("parent1", "parent2") if k in r]
        for p in parents:
            for c in children + adult_children:
                add(fid, p, c, "PARENT")
        if len(children) >= 2:
            add(fid, children[0], children[1], "SIBLING")

        if "grandparent" in r:
            gp = r["grandparent"]
            for p in parents:
                add(fid, gp, p, "PARENT")
            for c in children:
                add(fid, gp, c, "GRANDPARENT")

        if "sibling1" in r and "sibling2" in r:
            add(fid, r["sibling1"], r["sibling2"], "SIBLING")

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 6. 직업 / 잠재 행동
# -----------------------------------------------------------------------------
def assign_occupations(users: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = users.copy()
    occs = []
    for row in out.itertuples(index=False):
        occ = weighted_choice(rng, OCCUPATION_WEIGHTS_BY_AGE[row.age_group])
        occs.append(occ)
    out["occupation"] = occs
    out["occupation_group"] = out["occupation"].map(OCCUPATION_GROUP)
    out["plan_spending_score"] = out["occupation"].map(PLAN_SPENDING_SCORE).astype(float)
    return out


def assign_usage_profiles(users: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = users.copy()
    profiles = []
    content_affinity = []

    for row in out.itertuples(index=False):
        age = row.age
        if age <= 12:
            w = {"VERY_LOW": 0.30, "LOW": 0.35, "MEDIUM": 0.22, "HIGH": 0.10, "VERY_HIGH": 0.03}
        elif age <= 19:
            w = {"VERY_LOW": 0.08, "LOW": 0.17, "MEDIUM": 0.32, "HIGH": 0.28, "VERY_HIGH": 0.15}
        elif age <= 39:
            w = {"VERY_LOW": 0.04, "LOW": 0.10, "MEDIUM": 0.28, "HIGH": 0.35, "VERY_HIGH": 0.23}
        elif age <= 59:
            w = {"VERY_LOW": 0.06, "LOW": 0.18, "MEDIUM": 0.36, "HIGH": 0.27, "VERY_HIGH": 0.13}
        else:
            w = {"VERY_LOW": 0.18, "LOW": 0.32, "MEDIUM": 0.31, "HIGH": 0.15, "VERY_HIGH": 0.04}

        # 약한 직업 효과(합성 가정)
        if age >= 13 and row.occupation in {"학생", "전문직", "사무직"}:
            w["HIGH"] *= 1.15
            w["VERY_HIGH"] *= 1.10
        if row.occupation in {"은퇴", "무직"}:
            w["VERY_LOW"] *= 1.15
            w["LOW"] *= 1.10

        profile = weighted_choice(rng, w)
        profiles.append(profile)

        if age <= 19:
            ca = weighted_choice(rng, {"video": 0.30, "short_form": 0.28, "game": 0.20, "sns": 0.12, "music": 0.10})
        elif age <= 39:
            ca = weighted_choice(rng, {"video": 0.30, "sns": 0.20, "music": 0.18, "web": 0.12, "short_form": 0.12, "game": 0.08})
        elif age <= 59:
            ca = weighted_choice(rng, {"video": 0.28, "web": 0.25, "messaging": 0.16, "navigation": 0.12, "sns": 0.10, "music": 0.09})
        else:
            ca = weighted_choice(rng, {"video": 0.26, "messaging": 0.28, "web": 0.22, "navigation": 0.10, "music": 0.07, "sns": 0.07})
        content_affinity.append(ca)

    out["usage_profile"] = profiles
    out["content_affinity"] = content_affinity
    out["latent_daily_data_mb"] = out["usage_profile"].map(USAGE_PROFILE_DAILY_MB).astype(float)
    return out


# -----------------------------------------------------------------------------
# 7. 요금제 배정 / 초이스 혜택 선택
# -----------------------------------------------------------------------------
def age_benefit_id_for_age(age: int) -> Optional[str]:
    if age <= 18:
        return "AB10"
    if 19 <= age <= 34:
        return "AB20"
    if 65 <= age <= 74:
        return "AB30"
    if age >= 75:
        return "AB40"
    return None


def build_plan_age_lookup(plan_age_benefits: pd.DataFrame) -> Dict[Tuple[str, str], dict]:
    return {
        (str(r.plan_id), str(r.age_benefit_id)): r._asdict()
        for r in plan_age_benefits.itertuples(index=False)
    }


def effective_data_cap_for_age(plan: pd.Series, age: int,
                               age_lookup: Dict[Tuple[str, str], dict]) -> float:
    """적합도 점수용 유효 휴대폰 데이터 한도. 무제한은 +inf를 반환한다.

    무제한 요금제의 공유 데이터 연령 덤은 이미 무제한인 휴대폰 국내 데이터량을
    늘리지 않으므로 의도적으로 제외한다.
    """
    if bool(plan["is_unlimited"]):
        return float("inf")
    base = float(plan["data_limit_gb"]) if pd.notna(plan["data_limit_gb"]) else 0.0
    bid = age_benefit_id_for_age(age)
    if bid is None:
        return base
    plan_id = str(plan.get("plan_id", getattr(plan, "name", "")))
    row = age_lookup.get((plan_id, bid))
    return base + (float(row["bonus_data_gb"]) if row else 0.0)


def plan_score_for_user(user: pd.Series, plan: pd.Series,
                        age_lookup: Dict[Tuple[str, str], dict]) -> float:
    age = int(user["age"])
    monthly_need_gb = float(user["latent_daily_data_mb"] * 30.0 / 1024.0)
    spending = float(user["plan_spending_score"])
    target_fee = 30000 + 25000 * spending + min(40000, monthly_need_gb * 300)

    fee_distance = abs(math.log(max(plan["monthly_fee"], 1)) - math.log(max(target_fee, 1)))
    score = -2.6 * fee_distance

    effective_cap = effective_data_cap_for_age(plan, age, age_lookup)

    # 데이터 적합도가 핵심 신호이며 연령 덤은 effective_cap에 이미 반영됐다.
    if bool(plan["is_unlimited"]):
        if monthly_need_gb >= 80:
            score += 2.0
        elif monthly_need_gb >= 40:
            score += 0.8
        elif monthly_need_gb < 10:
            score -= 1.6
    else:
        cap = max(float(effective_cap), 0.05)
        ratio = monthly_need_gb / cap
        if 0.55 <= ratio <= 1.15:
            score += 2.2
        elif 0.25 <= ratio < 0.55:
            score += 0.9
        elif 1.15 < ratio <= 1.50:
            score -= 0.4
        elif ratio > 1.50:
            score -= 2.2
        else:
            score -= 0.8

    # 음성 중심 구간은 데이터 사용량이 매우 적은 고객에게만 개연성이 있다.
    if plan["plan_family"] == "VOICE":
        if monthly_need_gb <= max(effective_cap, 0.6) * 1.3:
            score += 1.2
        else:
            score -= 2.0

    # 이월은 명목 데이터 한도 차이가 아니라 완만한 행동 선호다.
    if bool(plan["is_rollover"]) and monthly_need_gb < max(effective_cap, 1.0):
        score += 0.10

    # 초이스/초이스 더블에서는 콘텐츠 성향과 지출 성향을 보조 신호로 사용한다.
    if bool(plan["is_choice_plan"]):
        if 19 <= age <= 39:
            score += 0.30
        if user["content_affinity"] in {"video", "music", "short_form"}:
            score += 0.50
        score += 0.45 * spending
        if plan["plan_family"] == "CHOICE_DOUBLE":
            score += 0.15 if spending >= 0.70 else -0.15

    # 콘텐츠 결합 선호가 없는 고사용량 고객에게는 무제한 베이직의 매력이 커진다.
    if plan["plan_name"] in {"베이직80", "베이직100"} and monthly_need_gb > 90:
        score += 0.45

    if bool(user.get("has_family", False)) and plan["monthly_fee"] >= 77000:
        score += 0.12

    return float(score)


def assign_plans(users: pd.DataFrame, plans: pd.DataFrame, plan_age_benefits: pd.DataFrame,
                 seed: int, suboptimal_ratio: float = SUBOPTIMAL_PLAN_RATIO) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = users.copy()
    plan_records = plans.set_index("plan_id")
    plan_ids = plans["plan_id"].tolist()
    age_lookup = build_plan_age_lookup(plan_age_benefits)

    assigned = []
    for _, user in out.iterrows():
        scores = np.array([
            plan_score_for_user(user, plan_records.loc[pid], age_lookup) for pid in plan_ids
        ])
        probs = safe_softmax(scores, temperature=0.78)
        assigned.append(str(rng.choice(plan_ids, p=probs)))
    out["current_plan_id"] = assigned
    out["is_suboptimal_seeded"] = False
    out["suboptimal_reason"] = None

    n_bad = int(round(len(out) * suboptimal_ratio))
    eligible_bad_indices = out.index[out["age"] >= 13].to_numpy()
    bad_indices = rng.choice(eligible_bad_indices, size=min(n_bad, len(eligible_bad_indices)), replace=False) if n_bad and len(eligible_bad_indices) else []

    moderate_low_cap_ids = plans[
        (~plans["is_unlimited"]) & (plans["data_limit_gb"] >= 7) & (plans["data_limit_gb"] <= 30)
    ]["plan_id"].tolist()
    extreme_low_cap_ids = plans[
        (~plans["is_unlimited"]) & (plans["data_limit_gb"] <= 4) & (plans["plan_family"] != "VOICE")
    ]["plan_id"].tolist()
    non_choice_ids = plans[
        (~plans["is_choice_plan"]) & (plans["is_unlimited"] | (plans["data_limit_gb"] >= 30))
    ]["plan_id"].tolist()

    high_fee_non_choice = plans[
        (plans["monthly_fee"] >= 65000) & (~plans["is_choice_plan"])
    ].copy()

    choice_candidates = plans[
        plans["is_choice_plan"]
    ].copy()

    for idx in bad_indices:
        u = out.loc[idx]
        age = int(u["age"])

        if age <= 18:
            bad_type = str(
                rng.choice(
                    ["HIGH_USAGE_LOW_PLAN", "VIDEO_NO_CHOICE"],
                    p=[0.55, 0.45]
                )
            )
        else:
            bad_type = str(
                rng.choice(
                    [
                        "HIGH_USAGE_LOW_PLAN",
                        "LOW_USAGE_HIGH_PLAN",
                        "VIDEO_NO_CHOICE",
                        "CHOICE_LOW_USAGE",
                    ],
                    p=[0.35, 0.20, 0.30, 0.15]
                )
            )

        if bad_type == "HIGH_USAGE_LOW_PLAN":
            out.at[idx, "usage_profile"] = "VERY_HIGH"
            out.at[idx, "latent_daily_data_mb"] = USAGE_PROFILE_DAILY_MB["VERY_HIGH"]

            pool = (
                extreme_low_cap_ids
                if rng.random() < 0.20
                else moderate_low_cap_ids
            )

            out.at[idx, "current_plan_id"] = str(
                rng.choice(pool)
            )

        elif bad_type == "LOW_USAGE_HIGH_PLAN":
            out.at[idx, "usage_profile"] = "LOW"
            out.at[idx, "latent_daily_data_mb"] = USAGE_PROFILE_DAILY_MB["LOW"]

            fees = high_fee_non_choice["monthly_fee"].to_numpy(dtype=float)

            weights = np.exp(
                -(fees - fees.min()) / 20000.0
            )
            weights /= weights.sum()

            out.at[idx, "current_plan_id"] = str(
                rng.choice(
                    high_fee_non_choice["plan_id"].to_numpy(),
                    p=weights
                )
            )

        elif bad_type == "VIDEO_NO_CHOICE":
            out.at[idx, "content_affinity"] = "video"

            out.at[idx, "usage_profile"] = str(
                rng.choice(["HIGH", "VERY_HIGH"])
            )

            out.at[idx, "latent_daily_data_mb"] = (
                USAGE_PROFILE_DAILY_MB[
                    out.at[idx, "usage_profile"]
                ]
            )

            candidate_plans = plans[
                (~plans["is_choice_plan"]) & (~plans["plan_family"].eq("VOICE"))
            ].copy()
            updated_user = out.loc[idx]
            scores = np.array([
                plan_score_for_user(updated_user, plan, age_lookup)
                for _, plan in candidate_plans.iterrows()
            ])

            probs = safe_softmax(scores, temperature=0.85)

            out.at[idx, "current_plan_id"] = str(
                rng.choice(candidate_plans["plan_id"].to_numpy(),p=probs)
            )

        else:  # 초이스 저활용 시나리오
            # 전체 데이터 사용량은 기존 사용 프로필을 유지한다.
            # 초이스 혜택과 관련된 콘텐츠만 이후 단계에서 저활용 처리한다.

            fees = choice_candidates["monthly_fee"].to_numpy(dtype=float)

            weights = np.exp(
                -(fees - fees.min()) / 20000.0
            )
            weights /= weights.sum()

            out.at[idx, "current_plan_id"] = str(
                rng.choice(
                    choice_candidates["plan_id"].to_numpy(),
                    p=weights
                )
            )

        out.at[idx, "is_suboptimal_seeded"] = True
        out.at[idx, "suboptimal_reason"] = bad_type

    return out


def assign_age_benefits(users: pd.DataFrame, plans: pd.DataFrame,
                        age_benefits: pd.DataFrame,
                        plan_age_benefits: pd.DataFrame) -> pd.DataFrame:
    out = users.copy()
    plan_map = plans.set_index("plan_id")
    age_map = age_benefits.set_index("age_benefit_id")
    lookup = build_plan_age_lookup(plan_age_benefits)

    current_ids = []
    names = []
    bonus_data = []
    bonus_shared = []
    bonus_voice = []
    bonus_sms = []
    bonus_video = []
    safety = []
    effective_data = []
    effective_shared = []

    for _, u in out.iterrows():
        pid = str(u["current_plan_id"])
        plan = plan_map.loc[pid]
        bid = age_benefit_id_for_age(int(u["age"]))
        row = lookup.get((pid, bid)) if bid else None
        if row is None:
            current_ids.append(None); names.append(None)
            bd = bs = bv = bsm = bvid = 0.0
            safe = False
        else:
            current_ids.append(bid)
            names.append(str(age_map.loc[bid, "benefit_name"]))
            bd = float(row["bonus_data_gb"])
            bs = float(row["bonus_shared_data_gb"])
            bv = float(row["bonus_voice_minutes"])
            bsm = float(row["bonus_sms_count"])
            bvid = float(row["bonus_video_minutes"])
            safe = bool(age_map.loc[bid, "includes_safety_box"])
        bonus_data.append(bd); bonus_shared.append(bs); bonus_voice.append(bv)
        bonus_sms.append(bsm); bonus_video.append(bvid); safety.append(safe)

        if bool(plan["is_unlimited"]):
            effective_data.append(np.nan)
        else:
            base = float(plan["data_limit_gb"]) if pd.notna(plan["data_limit_gb"]) else 0.0
            effective_data.append(round(base + bd, 3))
        effective_shared.append(round(float(plan["base_shared_data_gb"]) + bs, 3))

    out["current_age_benefit_id"] = current_ids
    out["current_age_benefit_name"] = names
    out["age_bonus_data_gb"] = bonus_data
    out["age_bonus_shared_data_gb"] = bonus_shared
    out["age_bonus_voice_minutes"] = bonus_voice
    out["age_bonus_sms_count"] = bonus_sms
    out["age_bonus_video_minutes"] = bonus_video
    out["age_benefit_safety_box"] = safety
    out["effective_data_gb"] = effective_data
    out["effective_shared_data_gb"] = effective_shared
    out["effective_data_unlimited"] = out["current_plan_id"].map(plan_map["is_unlimited"]).astype(bool)
    return out


def assign_choice_benefits(users: pd.DataFrame, plans: pd.DataFrame,
                           services: pd.DataFrame, plan_benefits: pd.DataFrame,
                           seed: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """선택한 초이스 혜택을 배정하고 정규화한 user_services 테이블을 반환한다.

    일반 초이스 요금제는 CHOICE 서비스 하나를 받는다. P3002/P3003은 PLUS 서비스
    하나를 추가로 받는다. 초이스 더블은 서로 다른 DOUBLE_CHOICE 서비스 두 개를
    합성 패키지 식별자 대신 두 행으로 저장한다.
    """
    rng = np.random.default_rng(seed)
    out = users.copy()
    plan_map = plans.set_index("plan_id")
    service_map = services.set_index("service_id")

    out["benefit_low_use_seeded"] = False
    rows: List[dict] = []
    seq = 1

    def service_weight(sid: str, affinity: str) -> float:
        cat = str(service_map.loc[sid, "service_category"])
        w = 1.0
        if affinity in {"video", "short_form"} and "video" in cat:
            w *= 3.0 if affinity == "video" else 1.8
        if affinity == "music" and cat in {"music", "video_music"}:
            w *= 3.0
        if affinity == "web" and cat in {"ebook", "ai"}:
            w *= 1.7
        return w

    def choose_many(pid: str, benefit_type: str, affinity: str, count: int,
                    exclude: Optional[set] = None) -> List[str]:
        exclude = exclude or set()
        options = plan_benefits[
            (plan_benefits["plan_id"] == pid) &
            (plan_benefits["benefit_type"] == benefit_type) &
            (plan_benefits["is_selectable"] == True)
        ]["service_id"].tolist()
        options = [sid for sid in options if sid not in exclude]
        if not options or count <= 0:
            return []

        chosen: List[str] = []
        available = list(options)
        for _ in range(min(count, len(available))):
            weights = np.asarray([service_weight(sid, affinity) for sid in available], dtype=float)
            weights /= weights.sum()
            sid = str(rng.choice(np.asarray(available, dtype=object), p=weights))
            chosen.append(sid)
            available.remove(sid)
        return chosen

    selected_value: Dict[str, float] = {}

    for idx, u in out.iterrows():
        pid = str(u["current_plan_id"])
        if not bool(plan_map.loc[pid, "is_choice_plan"]):
            selected_value[str(u["user_id"])] = 0.0
            continue

        uid = str(u["user_id"])
        affinity = str(u["content_affinity"])
        selected: List[Tuple[str, str]] = []

        if plan_map.loc[pid, "plan_family"] == "CHOICE_DOUBLE":
            for sid in choose_many(pid, "DOUBLE_CHOICE", affinity, 2):
                selected.append((sid, "DOUBLE_CHOICE"))
        else:
            primary = choose_many(pid, "CHOICE", affinity, 1)
            if primary:
                selected.append((primary[0], "CHOICE"))
            plus = choose_many(pid, "PLUS", affinity, 1, exclude=set(primary))
            if plus:
                selected.append((plus[0], "PLUS"))

        if rng.random() < 0.22 or u.get("suboptimal_reason") == "CHOICE_LOW_USAGE":
            out.at[idx, "benefit_low_use_seeded"] = True

        start_floor = pd.Timestamp(str(u.get("subscription_start_date", REFERENCE_DATE.date().isoformat())))
        selected_total = 0.0
        for sid, benefit_type in selected:
            candidate = REFERENCE_DATE - pd.DateOffset(months=int(rng.integers(0, 25)))
            start_date = max(start_floor, candidate).date().isoformat()
            rows.append({
                "user_service_id": f"US{seq:05d}",
                "user_id": uid,
                "service_id": sid,
                "benefit_type": benefit_type,
                "start_date": start_date,
            })
            seq += 1
            selected_total += float(service_map.loc[sid, "normal_monthly_price"])
        selected_value[uid] = selected_total

    user_services = pd.DataFrame(rows, columns=[
        "user_service_id", "user_id", "service_id", "benefit_type", "start_date"
    ])
    out["current_benefit_value"] = out["user_id"].map(selected_value).fillna(0.0).astype(float)
    return out, user_services


# -----------------------------------------------------------------------------
# 8. 가족결합 / 할인 혜택 적용
# -----------------------------------------------------------------------------
def _bundle_start_date(members: pd.DataFrame, rng: np.random.Generator) -> str:
    """가장 늦은 회선 개통일 이후의 현재 활성 결합 시작일을 생성한다."""
    latest_line_start = pd.to_datetime(members["subscription_start_date"]).max()
    sampled = REFERENCE_DATE - pd.DateOffset(months=int(rng.integers(1, 37)))
    return max(latest_line_start, sampled).date().isoformat()


def bundle_rule_amount(
    rules: pd.DataFrame,
    discount_id: str,
    method: str,
    rule_type: str,
    internet_group: str,
    contract_months: int,
    *,
    mobile_total: Optional[float] = None,
    mobile_line_fee: Optional[float] = None,
) -> float:
    """공식 구간표 규칙 하나를 찾아 정책 금액을 반환한다."""
    candidates = rules[
        (rules["discount_id"] == discount_id)
        & (rules["bundle_discount_method"] == method)
        & (rules["rule_type"] == rule_type)
        & (rules["contract_months"] == contract_months)
        & (rules["internet_product_group"].isin([internet_group, "ANY"]))
    ].copy()
    if mobile_total is not None:
        candidates = candidates[
            (candidates["mobile_total_fee_min"].isna() | (candidates["mobile_total_fee_min"] <= mobile_total))
            & (candidates["mobile_total_fee_max"].isna() | (mobile_total <= candidates["mobile_total_fee_max"]))
        ]
    if mobile_line_fee is not None:
        candidates = candidates[
            (candidates["mobile_line_fee_min"].isna() | (candidates["mobile_line_fee_min"] <= mobile_line_fee))
            & (candidates["mobile_line_fee_max"].isna() | (mobile_line_fee <= candidates["mobile_line_fee_max"]))
        ]
    if len(candidates) != 1:
        raise ValueError(
            f"결합 할인 규칙은 하나여야 합니다: {discount_id}/{method}/{rule_type}/"
            f"{internet_group}/{contract_months}; 조회 결과 {len(candidates)}개"
        )
    return float(candidates.iloc[0]["discount_amount"])


def bundle_method_policy_savings(
    members: pd.DataFrame,
    base_user_id: str,
    high_plan_fee: float,
    internet_group: str,
    contract_months: int,
    rules: pd.DataFrame,
    method: str,
    is_premium_bundle: bool,
) -> float:
    """합성 시나리오 선택에만 사용할 정책 구간표 기준 절감액을 계산한다.

    이 값은 의도적으로 일시값으로만 사용한다. output이나 사용자에 붙이지 않으며,
    임의 휴리스틱이 아닌 정책 테이블 기준으로 실제 비최적 방식을 생성하는 데 쓴다.
    """
    base_and_low = (
        members[(members["user_id"] == base_user_id) | (members["monthly_base_fee"] < high_plan_fee)]
        if is_premium_bundle else members
    )
    if method == "TOTAL":
        mobile_total = float(base_and_low["monthly_base_fee"].sum())
        mobile = bundle_rule_amount(rules, "D001", "TOTAL", "MOBILE_TOTAL_POOL", internet_group,
                                    contract_months, mobile_total=mobile_total)
        internet = bundle_rule_amount(rules, "D005", "TOTAL", "INTERNET_BASE", internet_group,
                                      contract_months, mobile_total=mobile_total)
    elif method == "FIXED":
        mobile = sum(
            bundle_rule_amount(rules, "D002", "FIXED", "MOBILE_LINE", internet_group, contract_months,
                               mobile_line_fee=float(fee))
            for fee in base_and_low["monthly_base_fee"]
        )
        internet = bundle_rule_amount(rules, "D005", "FIXED", "INTERNET_BASE", internet_group,
                                      contract_months)
    else:
        raise ValueError(f"지원하지 않는 결합 방식입니다: {method}")
    additional = bundle_rule_amount(rules, "D005", method, "INTERNET_ADDITIONAL", internet_group,
                                    contract_months)
    return float(mobile + internet + additional)


def assign_premium_family_bundles(
    families: pd.DataFrame,
    users: pd.DataFrame,
    plans: pd.DataFrame,
    internet_bundle_rules: pd.DataFrame,
    premium_family_rules: pd.DataFrame,
    seed: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """현재 프리미엄 가족결합 상태와 적용 혜택을 생성한다.

    `bundle_discount_compositions`에는 참여한 모든 인터넷/모바일 구성요소를 기록한다.
    `user_discounts`에는 사용자의 활성 혜택 사례만 기록하며 청구 할인금액은 넣지 않는다.
    """
    rng = np.random.default_rng(seed)
    fam = families.copy()
    out = users.copy()
    fee_map = plans.set_index("plan_id")["monthly_fee"].to_dict()
    network_map = plans.set_index("plan_id")["network_type"].to_dict()
    out["monthly_base_fee"] = out["current_plan_id"].map(fee_map).astype(float)
    out["network_type"] = out["current_plan_id"].map(network_map)
    additional_high_rule = premium_family_rules.loc[
        premium_family_rules["discount_id"] == "D003"
    ].iloc[0]
    youth_rule = premium_family_rules.loc[
        premium_family_rules["discount_id"] == "D004"
    ].iloc[0]

    family_columns = {
        "has_kt_internet": False,
        "internet_product_group": None,
        "internet_contract_months": None,
        "internet_status": "NONE",
        "bundle_discount_method": None,
        "total_discount_allocation_method": None,
        "internet_benefit_discount_id": None,
        "bundle_scenario": None,  # 내부 품질 점검용 라벨이며 내보내지 않는다.
    }
    for col, default in family_columns.items():
        fam[col] = default

    composition_rows: List[dict] = []
    entitlement_rows: List[dict] = []
    composition_seq = 1
    entitlement_seq = 1

    scenario_names = list(BUNDLE_SCENARIO_WEIGHTS)
    scenario_weights = np.array([BUNDLE_SCENARIO_WEIGHTS[name] for name in scenario_names], dtype=float)
    scenario_weights = scenario_weights / scenario_weights.sum()
    general_scenario_names = list(GENERAL_ACTIVE_BUNDLE_SCENARIO_WEIGHTS)
    general_scenario_weights = np.array(
        [GENERAL_ACTIVE_BUNDLE_SCENARIO_WEIGHTS[name] for name in general_scenario_names], dtype=float
    )
    general_scenario_weights = general_scenario_weights / general_scenario_weights.sum()
    internet_groups = list(INTERNET_PRODUCT_GROUP_WEIGHTS)
    internet_group_weights = np.array(
        [INTERNET_PRODUCT_GROUP_WEIGHTS[group] for group in internet_groups], dtype=float
    )
    internet_group_weights = internet_group_weights / internet_group_weights.sum()

    for family_idx, family in fam.iterrows():
        family_id = str(family["family_id"])
        members = out[out["family_id"] == family_id].copy()
        high_members = members[members["monthly_base_fee"] >= float(additional_high_rule["minimum_plan_fee"])].copy()
        is_premium_mobile_eligible = bool(
            len(high_members) >= int(additional_high_rule["minimum_high_line_count"])
            and len(members) <= int(additional_high_rule["maximum_mobile_line_count"])
        )

        # 프리미엄 적격 가족은 프리미엄 시나리오를 사용한다. 그 외 가족도 활성 인터넷이
        # 있으면 일반 인터넷-모바일 총액/정액 결합에 가입할 수 있다.
        if is_premium_mobile_eligible:
            scenario = str(rng.choice(scenario_names, p=scenario_weights))
            active_internet = scenario != "INTERNET_INACTIVE"
        else:
            active_internet = bool(rng.random() < INTERNET_ACTIVE_RATIO)
            scenario = (
                str(rng.choice(general_scenario_names, p=general_scenario_weights))
                if active_internet else "INTERNET_INACTIVE"
            )

        has_internet = active_internet or bool(rng.random() < 0.35)
        internet_status = "ACTIVE" if active_internet else ("SUSPENDED" if has_internet else "NONE")
        internet_group = (
            str(rng.choice(internet_groups, p=internet_group_weights))
            if has_internet else None
        )
        internet_contract_months = int(rng.choice([12, 24, 36], p=[0.10, 0.20, 0.70])) if has_internet else None
        is_premium_eligible = bool(
            is_premium_mobile_eligible and internet_group == "BASIC_ESSENCE_PREMIUM"
        )

        is_enrolled = bool(
            active_internet and scenario in {"OPTIMAL_ENROLLED", "SUBOPTIMAL_ENROLLED"}
        )
        bundle_type = (
            "PREMIUM_FAMILY" if is_enrolled and is_premium_eligible
            else "INTERNET_MOBILE" if is_enrolled
            else None
        )
        method = None
        total_allocation_method = None
        base_user_id = None
        bundle_start = None
        composition_by_user: Dict[str, str] = {}
        mobile_benefit_recipients: set[str] = set()

        if is_enrolled:
            # 프리미엄 가족결합은 공개된 자동 재지정 우선순위를 따른다. 일반 결합은 같은
            # 정렬 기준으로 대표 모바일 회선을 정하지만 할인 계산에는 모든 모바일을 포함한다.
            base_candidates = high_members if not high_members.empty else members
            base_member = base_candidates.sort_values(
                ["monthly_base_fee", "age", "subscription_start_date"],
                ascending=[True, False, True],
            ).iloc[0]
            base_user_id = str(base_member["user_id"])
            total_savings = bundle_method_policy_savings(
                members, base_user_id, float(additional_high_rule["minimum_plan_fee"]), str(internet_group), int(internet_contract_months),
                internet_bundle_rules, "TOTAL", bundle_type == "PREMIUM_FAMILY"
            )
            fixed_savings = bundle_method_policy_savings(
                members, base_user_id, float(additional_high_rule["minimum_plan_fee"]), str(internet_group), int(internet_contract_months),
                internet_bundle_rules, "FIXED", bundle_type == "PREMIUM_FAMILY"
            )
            preferred_method = "TOTAL" if total_savings > fixed_savings else "FIXED"
            # 절감액이 같은 방식을 의도적 비최적으로 분류하지 않는다. 특정 가족 구성에서
            # 실제 차이를 만들 수 없으면 시나리오 분포는 근사값이 된다.
            can_seed_nonoptimal = not math.isclose(total_savings, fixed_savings, abs_tol=0.001)
            method = preferred_method if scenario == "OPTIMAL_ENROLLED" or not can_seed_nonoptimal else (
                "FIXED" if preferred_method == "TOTAL" else "TOTAL"
            )
            base_and_low = (
                members[
                    (members["user_id"] == base_user_id)
                    | (members["monthly_base_fee"] < float(additional_high_rule["minimum_plan_fee"]))
                ]
                if bundle_type == "PREMIUM_FAMILY" else members
            )
            if method == "TOTAL":
                total_allocation_method = str(rng.choice(["EQUAL", "CONTRIBUTION"]))
                mobile_total = float(base_and_low["monthly_base_fee"].sum())
                mobile_amount = bundle_rule_amount(
                    internet_bundle_rules, "D001", "TOTAL", "MOBILE_TOTAL_POOL", str(internet_group),
                    int(internet_contract_months), mobile_total=mobile_total
                )
                if mobile_amount > 0:
                    mobile_benefit_recipients = set(base_and_low["user_id"])
            else:
                for recipient in base_and_low.itertuples(index=False):
                    amount = bundle_rule_amount(
                        internet_bundle_rules, "D002", "FIXED", "MOBILE_LINE", str(internet_group),
                        int(internet_contract_months), mobile_line_fee=float(recipient.monthly_base_fee)
                    )
                    if amount > 0:
                        mobile_benefit_recipients.add(str(recipient.user_id))
            bundle_start = _bundle_start_date(members, rng)

            # 베이스 인터넷은 같은 결합그룹의 구성요소이며 사용자 단위 모바일 혜택이 아니다.
            internet_composition_id = f"BC{composition_seq:06d}"
            composition_rows.append({
                "bundle_composition_id": internet_composition_id,
                "family_id": family_id,
                "component_type": "INTERNET",
                "user_id": None,
                "component_role": "BASE_INTERNET",
                "status": "ACTIVE",
                "start_date": bundle_start,
                "end_date": None,
            })
            composition_seq += 1

            for member_idx, member in members.iterrows():
                user_id = str(member["user_id"])
                if user_id == base_user_id:
                    role = "BASE_MOBILE"
                elif bundle_type == "PREMIUM_FAMILY" and float(member["monthly_base_fee"]) >= float(additional_high_rule["minimum_plan_fee"]):
                    role = "PREMIUM_MOBILE"
                else:
                    role = "LOW_MOBILE"
                composition_id = f"BC{composition_seq:06d}"
                composition_by_user[user_id] = composition_id
                composition_rows.append({
                    "bundle_composition_id": composition_id,
                    "family_id": family_id,
                    "component_type": "MOBILE",
                    "user_id": user_id,
                    "component_role": role,
                    "status": "ACTIVE",
                    "start_date": bundle_start,
                    "end_date": None,
                })
                composition_seq += 1

                discount_ids: List[str] = []
                if role in {"BASE_MOBILE", "LOW_MOBILE"}:
                    if user_id in mobile_benefit_recipients:
                        discount_ids.append("D001" if method == "TOTAL" else "D002")
                else:
                    discount_ids.append("D003")

                # 청소년 혜택에는 법정대리인 회선이 필요하다. 내부 가족 역할 모델에서는
                # 부모 역할로 표현하며, 일반 성인 친족만으로는 충족되지 않는다.
                guardian_lines = members[
                    members["family_role"].isin(["parent1", "parent2"])
                    & (members["monthly_base_fee"] >= float(youth_rule["guardian_minimum_plan_fee"]))
                    & (members["network_type"] == str(youth_rule["guardian_required_network_type"]))
                ]
                has_guardian = not guardian_lines.empty
                current_age = int(member["age"])
                enrollment_max_age = int(youth_rule["enrollment_max_age"])
                enrolled_before_age_limit = (
                    current_age <= enrollment_max_age
                    or pd.Timestamp(bundle_start) <= REFERENCE_DATE - pd.DateOffset(
                        years=current_age - enrollment_max_age
                    )
                )
                if (
                    bundle_type == "PREMIUM_FAMILY"
                    and has_guardian
                    and current_age >= int(youth_rule["enrollment_min_age"])
                    and current_age < int(youth_rule["benefit_end_age"])
                    and enrolled_before_age_limit
                    and float(member["monthly_base_fee"]) >= float(youth_rule["minimum_plan_fee"])
                    and str(member["network_type"]) == str(youth_rule["required_network_type"])
                ):
                    discount_ids.append("D004")

                for discount_id in discount_ids:
                    entitlement_rows.append({
                        "user_discount_id": f"UD{entitlement_seq:06d}",
                        "user_id": user_id,
                        "bundle_composition_id": composition_id,
                        "discount_id": discount_id,
                        "status": "ACTIVE",
                        "start_date": bundle_start,
                        "end_date": None,
                    })
                    entitlement_seq += 1

        fam.at[family_idx, "has_kt_internet"] = has_internet
        fam.at[family_idx, "internet_product_group"] = internet_group
        fam.at[family_idx, "internet_contract_months"] = internet_contract_months
        fam.at[family_idx, "internet_status"] = internet_status
        fam.at[family_idx, "has_bundle"] = is_enrolled
        fam.at[family_idx, "bundle_type"] = bundle_type
        fam.at[family_idx, "bundle_discount_method"] = method
        fam.at[family_idx, "total_discount_allocation_method"] = total_allocation_method
        fam.at[family_idx, "internet_benefit_discount_id"] = "D005" if is_enrolled else None
        fam.at[family_idx, "bundle_scenario"] = scenario

    compositions = pd.DataFrame(composition_rows, columns=[
        "bundle_composition_id", "family_id", "component_type", "user_id",
        "component_role", "status", "start_date", "end_date",
    ])
    user_discounts = pd.DataFrame(entitlement_rows, columns=[
        "user_discount_id", "user_id", "bundle_composition_id", "discount_id",
        "status", "start_date", "end_date",
    ])

    family_bundle_map = fam.set_index("family_id")["has_bundle"].to_dict() if not fam.empty else {}
    family_type_map = fam.set_index("family_id")["bundle_type"].to_dict() if not fam.empty else {}
    out["has_family_bundle"] = [
        bool(family_bundle_map.get(fid, False)) if pd.notna(fid) else False
        for fid in out["family_id"]
    ]
    out["family_bundle_type"] = [
        family_type_map.get(fid) if pd.notna(fid) else None
        for fid in out["family_id"]
    ]
    return fam, out, compositions, user_discounts


def calculate_current_total_discount_amount(
    users: pd.DataFrame,
    families: pd.DataFrame,
    compositions: pd.DataFrame,
    user_discounts: pd.DataFrame,
    internet_bundle_rules: pd.DataFrame,
    premium_family_rules: pd.DataFrame,
) -> pd.DataFrame:
    """현재 사용자가 받는 모바일 결합 할인 총액을 내부 정답값으로 계산한다.

    D001~D004 중 현재 활성 상태인 사용자 모바일 혜택만 합산한다. D005는 인터넷
    회선에 귀속되는 혜택이므로 제외하고, 선택약정 할인도 이 데이터의 비교 범위에
    포함하지 않는다. 계산 결과는 검증에만 사용하며 CSV로 내보내지 않는다.
    """
    out = users.copy()
    out["current_total_discount_amount"] = 0.0
    if user_discounts.empty:
        return out

    benefit_rows = user_discounts.copy()
    start_dates = pd.to_datetime(benefit_rows["start_date"])
    end_dates = pd.to_datetime(benefit_rows["end_date"])
    benefit_rows = benefit_rows[
        (benefit_rows["status"] == "ACTIVE")
        & (start_dates <= REFERENCE_DATE)
        & (end_dates.isna() | (end_dates >= REFERENCE_DATE))
    ].copy()
    if benefit_rows.empty:
        return out

    composition_family = compositions.set_index("bundle_composition_id")["family_id"]
    benefit_rows["family_id"] = benefit_rows["bundle_composition_id"].map(composition_family)
    if benefit_rows["family_id"].isna().any():
        raise ValueError("사용자 할인에서 결합 구성의 가족을 찾을 수 없습니다")

    unsupported = set(benefit_rows["discount_id"]) - {"D001", "D002", "D003", "D004"}
    if unsupported:
        raise ValueError(f"사용자 모바일 할인 총액으로 계산할 수 없는 혜택입니다: {sorted(unsupported)}")

    user_fee = out.set_index("user_id")["monthly_base_fee"].astype(float)
    family_map = families.set_index("family_id")
    premium_map = premium_family_rules.set_index("discount_id")
    calculated = pd.Series(0.0, index=out["user_id"], dtype=float)

    # 총액결합은 가족별 모바일 할인 풀을 균등 또는 기여도 기준으로 배분한다.
    total_rows = benefit_rows[benefit_rows["discount_id"] == "D001"]
    for family_id, rows in total_rows.groupby("family_id"):
        family = family_map.loc[family_id]
        recipient_fees = rows["user_id"].map(user_fee).astype(float)
        mobile_total = float(recipient_fees.sum())
        pool = bundle_rule_amount(
            internet_bundle_rules,
            "D001",
            "TOTAL",
            "MOBILE_TOTAL_POOL",
            str(family["internet_product_group"]),
            int(family["internet_contract_months"]),
            mobile_total=mobile_total,
        )
        allocation_method = str(family["total_discount_allocation_method"])
        if allocation_method == "EQUAL":
            amounts = pd.Series(pool / len(rows), index=rows["user_id"])
        elif allocation_method == "CONTRIBUTION":
            amounts = pd.Series(
                pool * recipient_fees.to_numpy() / mobile_total,
                index=rows["user_id"],
            )
        else:
            raise ValueError(f"지원하지 않는 총액결합 배분 방식입니다: {allocation_method}")
        calculated = calculated.add(amounts.groupby(level=0).sum(), fill_value=0.0)

    # 정액결합은 사용자 회선 요금 구간에 해당하는 고정 금액을 적용한다.
    for row in benefit_rows[benefit_rows["discount_id"] == "D002"].itertuples(index=False):
        family = family_map.loc[row.family_id]
        fee = float(user_fee.loc[row.user_id])
        amount = bundle_rule_amount(
            internet_bundle_rules,
            "D002",
            "FIXED",
            "MOBILE_LINE",
            str(family["internet_product_group"]),
            int(family["internet_contract_months"]),
            mobile_line_fee=fee,
        )
        calculated.loc[row.user_id] += amount

    # 프리미엄 추가 회선은 월정액의 25%, 청소년 혜택은 정책 고정액을 더한다.
    premium_rate = float(premium_map.loc["D003", "discount_rate"])
    youth_amount = float(premium_map.loc["D004", "discount_amount"])
    for user_id in benefit_rows.loc[benefit_rows["discount_id"] == "D003", "user_id"]:
        calculated.loc[user_id] += float(user_fee.loc[user_id]) * premium_rate
    for user_id in benefit_rows.loc[benefit_rows["discount_id"] == "D004", "user_id"]:
        calculated.loc[user_id] += youth_amount

    out["current_total_discount_amount"] = (
        out["user_id"].map(calculated).fillna(0.0).round(2).astype(float)
    )
    return out


# -----------------------------------------------------------------------------
# 9. 가입기간 + 가족 파생 특성
# -----------------------------------------------------------------------------
def assign_subscription_tenure(users: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = users.copy()
    months = []
    starts = []
    for age in out["age"]:
        # 합성 검증 규칙: 개인 이동통신 가입은 만 8세부터 가능하다고 가정한다.
        max_months = max(1, int((int(age) - 8) * 12 + 11))
        # 연령에 따른 상한이 있는 긴 꼬리 가입기간. 감마 분포로 중간 가입기간 다수와 긴 가입기간 일부를 만든다.
        sampled = int(min(max_months, max(1, round(rng.gamma(shape=2.1, scale=28.0)))))
        months.append(sampled)
        starts.append((REFERENCE_DATE - pd.DateOffset(months=sampled)).date().isoformat())
    out["subscription_months"] = months
    out["subscription_start_date"] = starts
    return out


def calculate_family_features(users: pd.DataFrame, families: pd.DataFrame) -> pd.DataFrame:
    out = users.copy()
    if families.empty:
        out["family_member_count"] = 0
        out["kt_family_member_count"] = 0
        out["eligible_for_family_bundle"] = False
        return out

    fam_map = families.set_index("family_id").to_dict("index")
    family_counts = []
    kt_counts = []
    eligible = []

    for _, u in out.iterrows():
        fid = u["family_id"]
        if pd.isna(fid):
            family_counts.append(0)
            kt_counts.append(0)
            eligible.append(False)
            continue

        f = fam_map[fid]
        members = out[out["family_id"] == fid]
        size = len(members)
        kt = size
        can_recommend = f["internet_status"] == "ACTIVE" and not bool(f["has_bundle"])

        family_counts.append(size)
        kt_counts.append(kt)
        eligible.append(can_recommend)

    out["family_member_count"] = family_counts
    out["kt_family_member_count"] = kt_counts
    out["eligible_for_family_bundle"] = eligible
    return out


# -----------------------------------------------------------------------------
# 10. 일별 사용량 / 콘텐츠 분배
# -----------------------------------------------------------------------------
def generate_daily_usage(users: pd.DataFrame, plans: pd.DataFrame,
                         n_days: int, seed: int) -> pd.DataFrame:
    """Generate observed daily use after quota-aware conservation behavior.

    Raw demand still comes from each user's latent usage profile. For finite
    plans, the observed amount decreases as cumulative monthly use approaches
    the effective allowance. One hidden warm-up month is simulated so the first
    exported partial month has realistic cumulative use and rollover state.
    """
    rng = np.random.default_rng(seed)
    output_dates = pd.date_range(end=REFERENCE_DATE - pd.Timedelta(days=1), periods=n_days, freq="D")
    first_month = output_dates[0].to_period("M").to_timestamp()
    warmup_start = first_month - pd.DateOffset(months=1)
    simulation_dates = pd.date_range(start=warmup_start, end=output_dates[-1], freq="D")
    output_date_set = set(output_dates)
    rollover_by_plan = plans.set_index("plan_id")["is_rollover"].astype(bool).to_dict()
    rows = []
    seq = 1

    for u in users.itertuples(index=False):
        base = float(u.latent_daily_data_mb)
        # 감마 분포: 양수·우측 치우침이며 평균은 shape × scale = base다.
        shape = 3.2
        scale = base / shape
        vals = rng.gamma(shape=shape, scale=scale, size=len(simulation_dates))

        # 주말 효과(합성 가정)는 저연령 사용자에게 더 크게 적용한다.
        weekend_mult = 1.14 if u.age <= 39 else 1.07
        weekend = np.array([d.weekday() >= 5 for d in simulation_dates])
        vals = vals * np.where(weekend, weekend_mult, 1.0)

        # 완만한 사용자별 노이즈를 더하고 비현실적 극단값은 제한한다.
        user_mult = float(np.clip(rng.lognormal(mean=0.0, sigma=0.16), 0.70, 1.45))
        vals = np.clip(vals * user_mult, 5.0, 25000.0)
        unlimited = bool(u.effective_data_unlimited)
        base_allowance_mb = (
            float(u.effective_data_gb) * 1024.0
            if not unlimited and pd.notna(u.effective_data_gb) else math.inf
        )
        is_rollover = bool(rollover_by_plan.get(str(u.current_plan_id), False))
        behavior = str(rng.choice(["EARLY", "NORMAL", "LATE"], p=[0.25, 0.55, 0.20]))
        thresholds = {
            "EARLY": (0.62, 0.78, 0.90),
            "NORMAL": (0.70, 0.85, 0.95),
            "LATE": (0.78, 0.92, 0.98),
        }[behavior]

        current_month = None
        allowance_mb = base_allowance_mb
        used_mb = 0.0
        carryover_mb = 0.0

        for d, raw_mb in zip(simulation_dates, vals):
            month = d.to_period("M")
            if current_month is None or month != current_month:
                if current_month is not None and is_rollover and math.isfinite(base_allowance_mb):
                    remaining = max(allowance_mb - used_mb, 0.0)
                    carryover_mb = min(remaining, base_allowance_mb)
                else:
                    carryover_mb = 0.0
                current_month = month
                allowance_mb = base_allowance_mb + carryover_mb
                used_mb = 0.0

            if unlimited:
                usage_ratio = np.nan
                quota_stage = "NORMAL"
                usage_mult = 1.0
            else:
                usage_ratio = used_mb / allowance_mb if allowance_mb > 0 else math.inf
                if usage_ratio >= 1.0:
                    quota_stage, usage_mult = "DEPLETED", 0.25
                elif usage_ratio >= thresholds[2]:
                    quota_stage, usage_mult = "CRITICAL", 0.55
                elif usage_ratio >= thresholds[1]:
                    quota_stage, usage_mult = "SAVE", 0.80
                elif usage_ratio >= thresholds[0]:
                    quota_stage, usage_mult = "WATCH", 0.95
                else:
                    quota_stage, usage_mult = "NORMAL", 1.0

            observed_mb = float(np.clip(raw_mb * usage_mult, 0.0, 25000.0))
            used_mb += observed_mb
            if d in output_date_set:
                rows.append((
                    f"DU{seq:08d}", u.user_id, d.date().isoformat(),
                    round(observed_mb, 3), quota_stage,
                    round(float(usage_ratio), 6) if math.isfinite(float(usage_ratio)) else np.nan,
                ))
                seq += 1

    return pd.DataFrame(rows, columns=[
        "usage_id", "user_id", "usage_date", "total_data_mb",
        "quota_stage", "quota_usage_ratio",
    ])


def base_content_weights(age: int, occupation: str) -> Dict[str, float]:
    # 합성 가정: 연령·직업은 콘텐츠 구성과 약하게 상관된다.
    if age <= 19:
        w = {"video": 0.22, "short_form": 0.22, "music": 0.10, "web": 0.06, "sns": 0.12,
             "messaging": 0.07, "game": 0.13, "video_call": 0.02, "navigation": 0.01, "cloud": 0.01, "other": 0.04}
    elif age <= 39:
        w = {"video": 0.25, "short_form": 0.12, "music": 0.11, "web": 0.12, "sns": 0.13,
             "messaging": 0.08, "game": 0.07, "video_call": 0.03, "navigation": 0.04, "cloud": 0.03, "other": 0.02}
    elif age <= 59:
        w = {"video": 0.24, "short_form": 0.06, "music": 0.07, "web": 0.19, "sns": 0.08,
             "messaging": 0.11, "game": 0.04, "video_call": 0.04, "navigation": 0.08, "cloud": 0.05, "other": 0.04}
    else:
        w = {"video": 0.23, "short_form": 0.04, "music": 0.05, "web": 0.20, "sns": 0.05,
             "messaging": 0.20, "game": 0.02, "video_call": 0.05, "navigation": 0.07, "cloud": 0.03, "other": 0.06}

    # 초이스 연계 AI·전자책 사용은 웹과 구분하되 여전히 제한적인 대분류로만 둔다.
    if age <= 19:
        w.update({"ai": 0.025, "ebook": 0.020})
    elif age <= 39:
        w.update({"ai": 0.035, "ebook": 0.020})
    elif age <= 59:
        w.update({"ai": 0.030, "ebook": 0.025})
    else:
        w.update({"ai": 0.015, "ebook": 0.020})

    if occupation == "학생":
        w["game"] *= 1.6; w["video"] *= 1.2; w["short_form"] *= 1.3
    if occupation == "운송직":
        w["navigation"] *= 2.5
    if occupation == "사무직":
        w["web"] *= 1.25; w["cloud"] *= 1.5
    if occupation == "전문직":
        w["web"] *= 1.3; w["cloud"] *= 1.5; w["video"] *= 1.08

    total = sum(w.values())
    return {k: v / total for k, v in w.items()}


def apply_choice_correlation(weights: Dict[str, float], service_category: Optional[str],
                             low_use_seeded: bool) -> Dict[str, float]:
    w = dict(weights)
    if service_category is None:
        return w
    # 받은 혜택과 관련 대분류 사이에는 약한 양의 상관만 둔다. 선택 서비스의
    # 구체적인 저활용 여부는 상세분류 가중치에서 처리한다.
    boost = 1.18 if not low_use_seeded else 1.0
    if service_category and "video" in service_category:
        w["video"] *= boost
        if service_category == "video_music":
            w["music"] *= boost
            w["short_form"] *= boost
    elif service_category == "music":
        w["music"] *= boost
    elif service_category == "ebook":
        w["ebook"] *= boost
    elif service_category == "ai":
        w["ai"] *= boost
    s = sum(w.values())
    return {k: max(v, 1e-6) / s for k, v in w.items()}


def detail_profile_for_user(rng: np.random.Generator, category: str,
                            selected_service_ids: Sequence[str],
                            low_use_seeded: bool) -> np.ndarray:
    """Return a sparse personal mix over the approved detail taxonomy."""
    details = CONTENT_DETAILS_BY_CATEGORY[category]
    if len(details) == 1:
        return np.array([1.0])

    configured = DETAIL_BASE_WEIGHTS[category]
    weights = np.array([configured[d] for d in details], dtype=float)
    detail_position = {detail: i for i, detail in enumerate(details)}
    for service_id in selected_service_ids:
        factor = 0.25 if low_use_seeded else 1.70
        for detail in SERVICE_DETAILS.get(service_id, []):
            if detail in detail_position:
                weights[detail_position[detail]] *= factor

    weights /= weights.sum()
    personal = rng.dirichlet(np.clip(weights * 12.0, 0.25, None))
    active_count = 2 if category in {"video", "music"} else 1
    active = np.argsort(personal)[-active_count:]
    sparse = np.zeros(len(details), dtype=float)
    sparse[active] = personal[active]
    sparse /= sparse.sum()
    return sparse


def generate_content_usage(users: pd.DataFrame, daily_usage: pd.DataFrame,
                           services: pd.DataFrame, user_services: pd.DataFrame,
                           n_days: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    service_cat = services.set_index("service_id")["service_category"].to_dict()
    selected_services = (
        user_services.groupby("user_id")["service_id"].apply(list).to_dict()
        if not user_services.empty else {}
    )
    all_frames = []
    seq_start = 1

    daily_groups = {uid: g.sort_values("usage_date") for uid, g in daily_usage.groupby("user_id", sort=False)}

    for u in users.itertuples(index=False):
        g = daily_groups[u.user_id]
        totals = g["total_data_mb"].to_numpy(dtype=float)
        weights = base_content_weights(int(u.age), str(u.occupation))
        selected = [str(sid) for sid in selected_services.get(str(u.user_id), [])]
        for sid in selected:
            weights = apply_choice_correlation(
                weights, service_cat.get(sid), bool(u.benefit_low_use_seeded)
            )

        # 월 소진 단계에 따라 영상·숏폼의 상대 비중을 낮춘 뒤 대분류를 배분한다.
        category_proportions = np.zeros((len(g), len(CONTENT_CATEGORIES)), dtype=float)
        stages = g["quota_stage"].to_numpy()
        for stage in np.unique(stages):
            mask = stages == stage
            adjusted = dict(weights)
            for category, multiplier in QUOTA_CONTENT_MULTIPLIERS[str(stage)].items():
                adjusted[category] *= multiplier
            base = np.array([adjusted[c] for c in CONTENT_CATEGORIES], dtype=float)
            base /= base.sum()
            alpha = np.clip(base * 45.0, 0.25, None)
            category_proportions[mask] = rng.dirichlet(alpha, size=int(mask.sum()))

        category_data = category_proportions * totals[:, None]
        data = np.zeros((len(g), len(CONTENT_DETAILS)), dtype=float)
        detail_offset = 0
        for category_index, category in enumerate(CONTENT_CATEGORIES):
            details = CONTENT_DETAILS_BY_CATEGORY[category]
            profile = detail_profile_for_user(
                rng, category, selected, bool(u.benefit_low_use_seeded)
            )
            active = np.flatnonzero(profile > 0)
            if len(active) == 1:
                data[:, detail_offset + active[0]] = category_data[:, category_index]
            else:
                detail_alpha = np.clip(profile[active] * 35.0, 0.25, None)
                detail_proportions = rng.dirichlet(detail_alpha, size=len(g))
                data[:, detail_offset + active] = (
                    detail_proportions * category_data[:, category_index, None]
                )
            detail_offset += len(details)

        data = np.round(data, 3)
        # 정확한 합계 보존을 위해 반올림 잔차는 일별 최대 카테고리에 넣는다.
        residual = totals - data.sum(axis=1)
        largest = np.argmax(data, axis=1)
        data[np.arange(len(g)), largest] += residual
        data = np.maximum(data, 0.0)

        repeated_details = np.tile(CONTENT_DETAILS, len(g))
        repeated_categories = np.tile(
            [
                category
                for category in CONTENT_CATEGORIES
                for _ in CONTENT_DETAILS_BY_CATEGORY[category]
            ],
            len(g),
        )
        flattened = data.reshape(-1)
        positive = flattened > 0
        row_count = int(positive.sum())
        frame = pd.DataFrame({
            "content_usage_id": [f"CU{i:09d}" for i in range(seq_start, seq_start + row_count)],
            "user_id": np.repeat(u.user_id, len(g) * len(CONTENT_DETAILS))[positive],
            "usage_date": np.repeat(g["usage_date"].to_numpy(), len(CONTENT_DETAILS))[positive],
            "content_category": repeated_categories[positive],
            "content_detail": repeated_details[positive],
            "data_usage_mb": flattened[positive],
        })
        all_frames.append(frame)
        seq_start += len(frame)

    return pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame(
        columns=[
            "content_usage_id", "user_id", "usage_date", "content_category",
            "content_detail", "data_usage_mb",
        ]
    )


# -----------------------------------------------------------------------------
# 11. 사용자 집계 특성
# -----------------------------------------------------------------------------
def calculate_user_features(users: pd.DataFrame, daily_usage: pd.DataFrame,
                            content_usage: pd.DataFrame) -> pd.DataFrame:
    out = users.copy()
    avg_daily = daily_usage.groupby("user_id")["total_data_mb"].mean()
    out["avg_daily_data_mb"] = out["user_id"].map(avg_daily).astype(float).round(2)
    out["monthly_estimated_data_gb"] = (out["avg_daily_data_mb"] * 30.0 / 1024.0).round(2)

    content_sum = content_usage.groupby(["user_id", "content_category"])["data_usage_mb"].sum()
    top = content_sum.groupby(level=0).idxmax().apply(lambda x: x[1]) if len(content_sum) else pd.Series(dtype=object)
    out["top_content_category"] = out["user_id"].map(top)
    return out


# -----------------------------------------------------------------------------
# 12. 검증
# -----------------------------------------------------------------------------
def _assert(condition: bool, message: str) -> None:
    if not bool(condition):
        raise AssertionError(message)


def validate_users(users: pd.DataFrame, plans: pd.DataFrame) -> List[str]:
    msgs = []
    _assert(users["current_plan_id"].isin(plans["plan_id"]).all(), "Invalid plan_id reference in users")
    msgs.append("1. users.current_plan_id FK: PASS")

    max_months = ((users["age"] - 8).clip(lower=0) * 12 + 11).clip(lower=1)
    _assert((users["subscription_months"] <= max_months).all(), "Unrealistic subscription_months")
    msgs.append("9. subscription tenure vs age: PASS")

    _assert((users.loc[~users["has_family"], "family_id"].isna()).all(), "No-family user has family_id")
    _assert((~users.loc[~users["has_family"], "has_family_bundle"]).all(), "No-family user has family bundle")
    msgs.append("11. no family bundle for family-less user: PASS")
    return msgs


def validate_family_relationships(users: pd.DataFrame, families: pd.DataFrame,
                                  relationships: pd.DataFrame) -> List[str]:
    msgs = []
    user_ids = set(users["user_id"])
    _assert(relationships["user_id"].isin(user_ids).all() and relationships["related_user_id"].isin(user_ids).all(),
            "Family relationship references non-existing user")
    msgs.append("2. family relationship user FKs: PASS")

    user_family = users.set_index("user_id")["family_id"].to_dict()
    same_family = relationships.apply(
        lambda r: user_family[r["user_id"]] == r["family_id"] == user_family[r["related_user_id"]], axis=1
    )
    _assert(same_family.all(), "Relationship connects users outside same family_id")
    msgs.append("3. relationship family consistency: PASS")

    _assert((relationships["user_id"] != relationships["related_user_id"]).all(), "Self relationship detected")
    msgs.append("4. no self relationship: PASS")

    ages = users.set_index("user_id")["age"].to_dict()
    for r in relationships.itertuples(index=False):
        a, b = int(ages[r.user_id]), int(ages[r.related_user_id])
        if r.relationship_type == "PARENT":
            _assert(a - b >= 18, f"Parent-child age gap invalid: {r.relationship_id}")
        elif r.relationship_type == "GRANDPARENT":
            _assert(a - b >= 36, f"Grandparent-grandchild age gap invalid: {r.relationship_id}")
        elif r.relationship_type == "SPOUSE":
            _assert(abs(a - b) <= 15, f"Spouse age gap too large: {r.relationship_id}")
        elif r.relationship_type == "SIBLING":
            _assert(abs(a - b) <= 15, f"Sibling age gap too large: {r.relationship_id}")
    msgs.append("5~7. family age rules: PASS")

    actual = users.dropna(subset=["family_id"]).groupby("family_id").size()
    declared = families.set_index("family_id")["family_size"]
    _assert(actual.astype(int).equals(declared.loc[actual.index].astype(int)), "family_size != actual users")
    msgs.append("8. family_size consistency: PASS")
    return msgs


def validate_discounts(users: pd.DataFrame, families: pd.DataFrame, plans: pd.DataFrame,
                       compositions: pd.DataFrame, user_discounts: pd.DataFrame,
                       discounts: pd.DataFrame, internet_rules: pd.DataFrame,
                       premium_rules: pd.DataFrame) -> List[str]:
    msgs = []
    _assert(set(discounts["discount_id"]) == {"D001", "D002", "D003", "D004", "D005"},
            "Premium Family benefit-case master is incomplete")
    _assert(user_discounts["discount_id"].isin(discounts["discount_id"]).all(), "Invalid discount_id")
    _assert(user_discounts["user_id"].isin(users["user_id"]).all(), "Discount references invalid user_id")
    _assert(user_discounts["bundle_composition_id"].isin(compositions["bundle_composition_id"]).all(),
            "Discount references invalid bundle composition")
    _assert(~user_discounts.duplicated(["user_id", "discount_id", "bundle_composition_id", "start_date"]).any(),
            "Duplicate user discount entitlement")

    users_with_plan = users.merge(
        plans[["plan_id", "network_type"]],
        left_on="current_plan_id", right_on="plan_id", how="left",
        validate="many_to_one",
    )
    _assert(users_with_plan["network_type"].notna().all(),
            "사용자 요금제의 망 유형을 찾을 수 없습니다")
    user_map = users_with_plan.set_index("user_id")
    composition_map = compositions.set_index("bundle_composition_id") if not compositions.empty else pd.DataFrame()
    additional_high_rule = premium_rules.loc[premium_rules["discount_id"] == "D003"].iloc[0]
    youth_rule = premium_rules.loc[premium_rules["discount_id"] == "D004"].iloc[0]
    high_fee = float(additional_high_rule["minimum_plan_fee"])
    internet_families = families[families["has_kt_internet"]]
    _assert(internet_families["internet_product_group"].isin({
        "BASIC_ESSENCE_PREMIUM", "SLIM",
    }).all(), "Internet family has an unsupported discount group")
    _assert(families.loc[~families["has_kt_internet"], "internet_product_group"].isna().all(),
            "Family without internet has an internet discount group")

    for f in families.loc[families["has_bundle"]].itertuples(index=False):
        _assert(bool(f.has_kt_internet) and f.internet_status == "ACTIVE",
                f"Bundled family has no active KT internet: {f.family_id}")
        _assert(f.internet_product_group in {"BASIC_ESSENCE_PREMIUM", "SLIM"},
                f"Unsupported generated internet discount group: {f.family_id}")
        _assert(int(f.internet_contract_months) in {12, 24, 36},
                f"Missing internet contract term: {f.family_id}")
        _assert(f.bundle_type in {"PREMIUM_FAMILY", "INTERNET_MOBILE"},
                f"Unexpected bundle type: {f.family_id}")
        is_premium_bundle = f.bundle_type == "PREMIUM_FAMILY"
        _assert(f.bundle_discount_method in {"TOTAL", "FIXED"}, f"Missing bundle method: {f.family_id}")
        if f.bundle_discount_method == "TOTAL":
            _assert(f.total_discount_allocation_method in {"EQUAL", "CONTRIBUTION"},
                    f"Missing TOTAL allocation method: {f.family_id}")
        else:
            _assert(pd.isna(f.total_discount_allocation_method),
                    f"FIXED bundle has TOTAL allocation method: {f.family_id}")
        _assert(f.internet_benefit_discount_id == "D005", f"Missing internet benefit: {f.family_id}")

        family_components = compositions[compositions["family_id"] == f.family_id]
        _assert(int((family_components["component_role"] == "BASE_INTERNET").sum()) == 1,
                f"Bundled family must have one base internet: {f.family_id}")
        mobile_components = family_components[family_components["component_type"] == "MOBILE"]
        family_users = users_with_plan[users_with_plan["family_id"] == f.family_id]
        _assert(set(mobile_components["user_id"]) == set(family_users["user_id"]),
                f"Bundle composition must include every family mobile line: {f.family_id}")
        _assert(int((mobile_components["component_role"] == "BASE_MOBILE").sum()) == 1,
                f"Bundled family must have one base mobile: {f.family_id}")

        high_users = family_users[family_users["monthly_base_fee"] >= high_fee]
        base_user_id = str(mobile_components.loc[
            mobile_components["component_role"] == "BASE_MOBILE", "user_id"
        ].iloc[0])
        if is_premium_bundle:
            _assert(len(high_users) >= 2, f"Premium family has fewer than two high lines: {f.family_id}")
            _assert(f.internet_product_group == "BASIC_ESSENCE_PREMIUM",
                    f"Premium family requires the higher internet discount group: {f.family_id}")
            _assert(float(user_map.loc[base_user_id, "monthly_base_fee"]) >= high_fee,
                    f"Premium base mobile is not a high plan: {f.family_id}")
        else:
            _assert(len(high_users) < 2 or f.internet_product_group == "SLIM",
                    f"General bundle should not satisfy every premium-family condition: {f.family_id}")
            _assert(not (mobile_components["component_role"] == "PREMIUM_MOBILE").any(),
                    f"General bundle has a premium mobile role: {f.family_id}")

        expected_base_discount = "D001" if f.bundle_discount_method == "TOTAL" else "D002"
        base_low_components = mobile_components[
            mobile_components["component_role"].isin(["BASE_MOBILE", "LOW_MOBILE"])
        ]
        base_low_discount_rows = user_discounts[
            user_discounts["bundle_composition_id"].isin(base_low_components["bundle_composition_id"])
            & (user_discounts["discount_id"] == expected_base_discount)
        ]
        if f.bundle_discount_method == "TOTAL":
            mobile_total = sum(
                float(user_map.loc[c.user_id, "monthly_base_fee"])
                for c in base_low_components.itertuples(index=False)
            )
            expected_total_recipients = len(base_low_components) if bundle_rule_amount(
                internet_rules, "D001", "TOTAL", "MOBILE_TOTAL_POOL",
                str(f.internet_product_group), int(f.internet_contract_months),
                mobile_total=mobile_total,
            ) > 0 else 0
            _assert(len(base_low_discount_rows) == expected_total_recipients,
                    f"TOTAL allocation recipient mismatch: {f.family_id}; "
                    f"actual={len(base_low_discount_rows)}, expected={expected_total_recipients}, "
                    f"mobile_total={mobile_total}")
        else:
            expected_fixed_recipients = sum(
                float(user_map.loc[c.user_id, "monthly_base_fee"]) >= 37000
                for c in base_low_components.itertuples(index=False)
            )
            _assert(len(base_low_discount_rows) == expected_fixed_recipients,
                    f"FIXED benefit recipients must match positive-rate mobile lines: {f.family_id}")
        for component in mobile_components.itertuples(index=False):
            row_discounts = set(user_discounts.loc[
                user_discounts["bundle_composition_id"] == component.bundle_composition_id,
                "discount_id",
            ])
            fee = float(user_map.loc[component.user_id, "monthly_base_fee"])
            if component.component_role in {"BASE_MOBILE", "LOW_MOBILE"}:
                _assert("D003" not in row_discounts,
                        f"Base/low line cannot receive additional-high benefit: {component.user_id}")
                _assert((row_discounts & {"D001", "D002"}) <= {expected_base_discount},
                        f"Base/low line has incompatible bundle method benefit: {component.user_id}")
            else:
                _assert(fee >= high_fee and "D003" in row_discounts,
                        f"Additional high line missing 25% benefit: {component.user_id}")
                _assert("D001" not in row_discounts and "D002" not in row_discounts,
                        f"Additional high line cannot receive total/fixed benefit: {component.user_id}")
            if "D004" in row_discounts:
                user = user_map.loc[component.user_id]
                benefit_start = pd.Timestamp(user_discounts.loc[
                    (user_discounts["bundle_composition_id"] == component.bundle_composition_id)
                    & (user_discounts["discount_id"] == "D004"),
                    "start_date",
                ].iloc[0])
                current_age = int(user.age)
                enrollment_max_age = int(youth_rule["enrollment_max_age"])
                enrolled_before_age_limit = (
                    current_age <= enrollment_max_age
                    or benefit_start <= REFERENCE_DATE - pd.DateOffset(
                        years=current_age - enrollment_max_age
                    )
                )
                _assert(
                    is_premium_bundle
                    and current_age >= int(youth_rule["enrollment_min_age"])
                    and current_age < int(youth_rule["benefit_end_age"])
                    and enrolled_before_age_limit
                    and float(user.monthly_base_fee) >= float(youth_rule["minimum_plan_fee"])
                    and user.network_type == youth_rule["required_network_type"],
                        f"Youth benefit eligibility mismatch: {component.user_id}")
                guardian_lines = family_users[
                    family_users["family_role"].isin(["parent1", "parent2"])
                    & (family_users["monthly_base_fee"] >= float(youth_rule["guardian_minimum_plan_fee"]))
                    & (family_users["network_type"] == youth_rule["guardian_required_network_type"])
                ]
                _assert(not guardian_lines.empty, f"Youth benefit has no eligible legal-guardian line: {component.user_id}")

    # 활성 결합이 아닌 가족에는 혜택 적용 행이 존재할 수 없다.
    for row in user_discounts.itertuples(index=False):
        component = composition_map.loc[row.bundle_composition_id]
        _assert(component.component_type == "MOBILE" and component.user_id == row.user_id,
                f"User discount must target its own mobile component: {row.user_discount_id}")
        _assert(bool(families.loc[families["family_id"] == component.family_id, "has_bundle"].iloc[0]),
                f"Discount exists for unbundled family: {component.family_id}")

    _assert("current_total_discount_amount" in users.columns,
            "내부 사용자별 현재 총 할인액이 계산되지 않았습니다")
    _assert(users["current_total_discount_amount"].notna().all(),
            "내부 사용자별 현재 총 할인액에 결측값이 있습니다")
    _assert((users["current_total_discount_amount"] >= 0).all(),
            "내부 사용자별 현재 총 할인액에 음수가 있습니다")
    discount_start = pd.to_datetime(user_discounts["start_date"])
    discount_end = pd.to_datetime(user_discounts["end_date"])
    active_discount_users = set(user_discounts.loc[
        (user_discounts["status"] == "ACTIVE")
        & (discount_start <= REFERENCE_DATE)
        & (discount_end.isna() | (discount_end >= REFERENCE_DATE)),
        "user_id",
    ])
    positive_amount_users = set(users.loc[
        users["current_total_discount_amount"] > 0, "user_id"
    ])
    _assert(active_discount_users == positive_amount_users,
            "활성 할인 혜택 사용자와 내부 총 할인액 양수 사용자가 일치하지 않습니다")

    msgs.append("12. internet/mobile bundle composition and benefit entitlements: PASS")
    msgs.append("12-1. internal current mobile discount totals: PASS (D001~D004)")
    no_bundle_candidates = int((families["bundle_scenario"].isin([
        "INTERNET_ACTIVE_NOT_ENROLLED", "INTERNET_INACTIVE"
    ])).sum())
    msgs.append(f"13. bundle missed-opportunity scenarios: PASS ({no_bundle_candidates} families)")
    return msgs


def validate_bundle_policy_rules(discounts: pd.DataFrame, internet_rules: pd.DataFrame,
                                 premium_rules: pd.DataFrame) -> List[str]:
    """출력한 정책 구간표의 참조 및 범위 정합성을 검증한다."""
    msgs = []
    _assert(internet_rules["discount_id"].isin(discounts["discount_id"]).all(),
            "Internet bundle rule references unknown discount")
    _assert(premium_rules["discount_id"].isin(discounts["discount_id"]).all(),
            "Premium family rule references unknown discount")
    _assert(~internet_rules.duplicated([
        "discount_id", "bundle_discount_method", "rule_type", "internet_product_group",
        "contract_months", "mobile_total_fee_min", "mobile_line_fee_min",
    ]).any(), "Duplicate internet bundle policy rule")
    _assert((internet_rules["contract_months"].isin([12, 24, 36])).all(),
            "Unsupported internet contract term in policy rules")
    _assert((internet_rules["discount_amount"] >= 0).all(), "Negative internet policy amount")
    _assert(set(premium_rules["discount_id"]) == {"D003", "D004"},
            "Premium family policy cases must be D003/D004")
    _assert(float(premium_rules.loc[premium_rules["discount_id"] == "D003", "discount_rate"].iloc[0]) == 0.25,
            "Premium additional-line rate must be 25%")
    _assert(float(premium_rules.loc[premium_rules["discount_id"] == "D004", "discount_amount"].iloc[0]) == 5500.0,
            "Premium youth policy amount must be KRW 5,500")
    youth_rule = premium_rules.loc[premium_rules["discount_id"] == "D004"].iloc[0]
    _assert(int(youth_rule["enrollment_max_age"]) == 18 and int(youth_rule["benefit_end_age"]) == 20,
            "Premium youth enrollment/end-age policy mismatch")
    msgs.append("16. internet/premium-family policy master FKs + official core rates: PASS")
    return msgs


def validate_usage(daily_usage: pd.DataFrame, content_usage: pd.DataFrame) -> List[str]:
    msgs = []
    daily_sum = daily_usage.set_index(["user_id", "usage_date"])["total_data_mb"].sort_index()
    content_sum = content_usage.groupby(["user_id", "usage_date"])["data_usage_mb"].sum().sort_index()
    joined = pd.concat([daily_sum.rename("daily"), content_sum.rename("content")], axis=1)
    max_err = float((joined["daily"] - joined["content"]).abs().max())
    _assert(max_err <= 0.01, f"Daily/content usage mismatch, max error={max_err}")
    msgs.append(f"10. daily_usage == content_usage sum: PASS (max_error={max_err:.6f} MB)")
    expected_detail_category = {
        detail: category
        for category, details in CONTENT_DETAILS_BY_CATEGORY.items()
        for detail in details
    }
    _assert(content_usage["content_category"].isin(CONTENT_CATEGORIES).all(),
            "content_usage has invalid content_category")
    _assert(content_usage["content_detail"].isin(expected_detail_category).all(),
            "content_usage has invalid content_detail")
    actual_parent = content_usage["content_detail"].map(expected_detail_category)
    _assert(actual_parent.eq(content_usage["content_category"]).all(),
            "content_detail does not match content_category")
    _assert(~content_usage.duplicated(
        ["user_id", "usage_date", "content_category", "content_detail"]
    ).any(), "Duplicate content usage grain")
    _assert(daily_usage["quota_stage"].isin(QUOTA_CONTENT_MULTIPLIERS).all(),
            "daily_usage has invalid quota_stage")
    msgs.append("11. content category/detail taxonomy + composite grain: PASS")
    return msgs


def validate_master_relations(plans: pd.DataFrame, services: pd.DataFrame,
                              plan_benefits: pd.DataFrame,
                              age_benefits: pd.DataFrame,
                              plan_age_benefits: pd.DataFrame,
                              users: pd.DataFrame,
                              user_services: pd.DataFrame) -> List[str]:
    msgs = []
    _assert(plan_benefits["plan_id"].isin(plans["plan_id"]).all(), "plan_benefits has invalid plan_id")
    _assert(plan_benefits["service_id"].isin(services["service_id"]).all(), "plan_benefits has invalid service_id")
    _assert(plan_age_benefits["plan_id"].isin(plans["plan_id"]).all(), "plan_age_benefits has invalid plan_id")
    _assert(plan_age_benefits["age_benefit_id"].isin(age_benefits["age_benefit_id"]).all(),
            "plan_age_benefits has invalid age_benefit_id")
    _assert(~plan_age_benefits.duplicated(["plan_id", "age_benefit_id"]).any(),
            "Duplicate plan-age benefit row")
    msgs.append("14~15. plan/service/age-benefit FKs + uniqueness: PASS")

    # 요금제 코드 계열 접두어 규칙.
    prefix = {"VOICE": "P10", "BASIC_ROLLOVER": "P21", "BASIC": "P22", "CHOICE": "P30", "CHOICE_DOUBLE": "P40"}
    for r in plans.itertuples(index=False):
        _assert(str(r.plan_id).startswith(prefix[str(r.plan_family)]),
                f"Plan code prefix mismatch: {r.plan_id} / {r.plan_family}")
    msgs.append("plan ID family-prefix convention: PASS")

    # 모든 초이스 계열에는 선택 가능한 혜택 묶음이 있어야 한다.
    normal_choice = set(plans.loc[plans["plan_family"] == "CHOICE", "plan_id"])
    normal_benefit = set(plan_benefits.loc[
        (plan_benefits["benefit_type"] == "CHOICE") & plan_benefits["is_selectable"], "plan_id"
    ])
    _assert(normal_choice.issubset(normal_benefit), f"Choice plan without selectable benefit: {normal_choice-normal_benefit}")
    double_choice = set(plans.loc[plans["plan_family"] == "CHOICE_DOUBLE", "plan_id"])
    double_benefit = set(plan_benefits.loc[
        (plan_benefits["benefit_type"] == "DOUBLE_CHOICE") & plan_benefits["is_selectable"], "plan_id"
    ])
    _assert(double_choice.issubset(double_benefit), f"Choice Double without selectable package: {double_choice-double_benefit}")
    msgs.append("Choice selectable benefits: PASS")

    # 사용자가 선택한 혜택은 user_services로 정규화한다.
    if not user_services.empty:
        _assert(user_services["user_id"].isin(users["user_id"]).all(),
                "user_services has invalid user_id")
        _assert(user_services["service_id"].isin(services["service_id"]).all(),
                "user_services has invalid service_id")
        _assert(~user_services.duplicated(["user_id", "service_id"]).any(),
                "Duplicate user/service selection")

        plan_by_user = users.set_index("user_id")["current_plan_id"].to_dict()
        selectable = set(zip(
            plan_benefits.loc[plan_benefits["is_selectable"], "plan_id"],
            plan_benefits.loc[plan_benefits["is_selectable"], "service_id"],
            plan_benefits.loc[plan_benefits["is_selectable"], "benefit_type"],
        ))
        for r in user_services.itertuples(index=False):
            pid = plan_by_user[r.user_id]
            _assert((pid, r.service_id, r.benefit_type) in selectable,
                    f"Selected service not offered by current plan: {r.user_id} / {r.service_id}")

    plan_family = plans.set_index("plan_id")["plan_family"].to_dict()
    selections = user_services.groupby(["user_id", "benefit_type"]).size() if not user_services.empty else pd.Series(dtype=int)
    for r in users.itertuples(index=False):
        family = plan_family[str(r.current_plan_id)]
        if family == "CHOICE_DOUBLE":
            count = int(selections.get((r.user_id, "DOUBLE_CHOICE"), 0))
            _assert(count == 2, f"Choice Double user must have exactly 2 services: {r.user_id}")
        elif family == "CHOICE":
            count = int(selections.get((r.user_id, "CHOICE"), 0))
            _assert(count == 1, f"Choice user must have exactly 1 primary service: {r.user_id}")
        else:
            count = int(user_services.loc[user_services["user_id"] == r.user_id].shape[0])
            _assert(count == 0, f"Non-Choice user has selected Choice service: {r.user_id}")
    msgs.append("user_services selection/FKs/counts: PASS")

    # 연령 혜택 배정은 연령 및 요금제 혜택 제공 여부와 일치해야 한다.
    age_master = age_benefits.set_index("age_benefit_id")
    pab = set(zip(plan_age_benefits["plan_id"], plan_age_benefits["age_benefit_id"]))
    for r in users.itertuples(index=False):
        if not isinstance(r.current_age_benefit_id, str):
            continue
        _assert((r.current_plan_id, r.current_age_benefit_id) in pab,
                f"Age benefit not supported by plan: {r.user_id}")
        a = age_master.loc[r.current_age_benefit_id]
        _assert(int(r.age) >= int(a.min_age), f"Age benefit min-age mismatch: {r.user_id}")
        if pd.notna(a.max_age):
            _assert(int(r.age) <= int(a.max_age), f"Age benefit max-age mismatch: {r.user_id}")
    msgs.append("age-benefit eligibility: PASS")
    return msgs


def run_all_validations(users: pd.DataFrame, families: pd.DataFrame,
                        relationships: pd.DataFrame, plans: pd.DataFrame,
                        services: pd.DataFrame, plan_benefits: pd.DataFrame,
                        age_benefits: pd.DataFrame, plan_age_benefits: pd.DataFrame,
                        discounts: pd.DataFrame, compositions: pd.DataFrame,
                        user_discounts: pd.DataFrame,
                        user_services: pd.DataFrame,
                        internet_bundle_rules: pd.DataFrame,
                        premium_family_rules: pd.DataFrame,
                        daily_usage: pd.DataFrame, content_usage: pd.DataFrame) -> None:
    print("\n=== VALIDATION ===")
    messages: List[str] = []
    messages += validate_users(users, plans)
    messages += validate_family_relationships(users, families, relationships)
    messages += validate_discounts(
        users, families, plans, compositions, user_discounts, discounts,
        internet_bundle_rules, premium_family_rules
    )
    messages += validate_bundle_policy_rules(discounts, internet_bundle_rules, premium_family_rules)
    messages += validate_usage(daily_usage, content_usage)
    messages += validate_master_relations(
        plans, services, plan_benefits, age_benefits, plan_age_benefits, users, user_services
    )
    for m in messages:
        print("[PASS]", m)


# -----------------------------------------------------------------------------
# 13. 요약 / 출력
# -----------------------------------------------------------------------------
def _print_ratio_table(series: pd.Series, title: str) -> None:
    counts = series.value_counts(dropna=False)
    ratio = (counts / len(series) * 100).round(1)
    df = pd.DataFrame({"count": counts, "ratio_pct": ratio})
    print(f"\n[{title}]\n{df.to_string()}")


def print_summary(users: pd.DataFrame, families: pd.DataFrame, plans: pd.DataFrame,
                  user_discounts: pd.DataFrame, user_services: pd.DataFrame,
                  services: pd.DataFrame, content_usage: pd.DataFrame) -> None:
    print("\n=== GENERATION SUMMARY ===")
    print(f"총 사용자 수: {len(users):,}")
    _print_ratio_table(users["age_group"], "연령대별 사용자")
    _print_ratio_table(users["occupation"], "직업별 사용자")

    merged = users.merge(plans[["plan_id", "plan_name", "plan_family", "price_band", "is_choice_plan"]],
                         left_on="current_plan_id", right_on="plan_id", how="left")
    _print_ratio_table(merged["plan_name"], "요금제별 사용자")
    _print_ratio_table(merged["price_band"], "가격대별 사용자")
    _print_ratio_table(merged["plan_family"], "요금제 패밀리별 사용자")
    _print_ratio_table(users["current_age_benefit_name"], "연령별 덤 혜택 적용 사용자")

    print("\n[연령대 × 요금제 상위 분포]")
    print(pd.crosstab(merged["age_group"], merged["plan_name"]).to_string())
    print("\n[직업 × 가격대]")
    print(pd.crosstab(merged["occupation"], merged["price_band"]).to_string())

    print(f"\n평균 일 데이터 사용량: {users['avg_daily_data_mb'].mean():,.1f} MB")
    print(f"평균 월 예상 데이터 사용량: {users['monthly_estimated_data_gb'].mean():,.1f} GB")
    print("\n[연령대별 평균 월 데이터 GB]")
    print(users.groupby("age_group")["monthly_estimated_data_gb"].mean().round(1).to_string())
    print("\n[요금제별 평균 월 데이터 GB]")
    print(merged.groupby("plan_name")["monthly_estimated_data_gb"].mean().round(1).sort_values().to_string())

    content_total = content_usage.groupby("content_category")["data_usage_mb"].sum().sort_values(ascending=False)
    print("\n[콘텐츠별 총 데이터 사용량 GB]")
    print((content_total / 1024.0).round(1).to_string())

    family_user_ratio = users["has_family"].mean() * 100
    print(f"\n가족이 있는 사용자 비율: {family_user_ratio:.1f}%")
    print(f"가족 수: {len(families):,}")
    if len(families):
        print(f"평균 가족 구성원 수: {families['family_size'].mean():.2f}")
        print("가족 구성원 수별 분포:")
        print(families["family_size"].value_counts().sort_index().to_string())
        print(f"결합할인 가입 가족 비율: {families['has_bundle'].mean() * 100:.1f}%")
    print(f"가족은 있으나 결합할인 미가입 사용자 수: {((users['has_family']) & (~users['has_family_bundle'])).sum():,}")
    print("같은 가족 내 KT 사용자 수 분포:")
    print(users.loc[users["has_family"], "kt_family_member_count"].value_counts().sort_index().to_string())
    print(f"가족결합 추천 후보자 수: {users['eligible_for_family_bundle'].sum():,}")

    if user_discounts.empty:
        print("할인 이용자: 없음")
    else:
        print("\n[할인 종류별 이용자 수]")
        print(user_discounts.groupby("discount_id")["user_id"].nunique().to_string())
        discounted_users = users[users["current_total_discount_amount"] > 0]
        print("\n[내부 검증용 현재 모바일 결합 할인액]")
        print(f"총 할인액: {discounted_users['current_total_discount_amount'].sum():,.2f}원")
        print(f"할인 사용자 평균: {discounted_users['current_total_discount_amount'].mean():,.2f}원")
        print("계산 범위: D001~D004 (D005 인터넷 회선 혜택·선택약정 제외)")

    if user_services.empty:
        print("선택 부가서비스 이용자: 없음")
    else:
        service_summary = (
            user_services.merge(services[["service_id", "service_name"]], on="service_id", how="left")
            .groupby(["benefit_type", "service_name"])["user_id"]
            .nunique()
            .sort_values(ascending=False)
        )
        print("\n[선택 부가서비스 이용자 수]")
        print(service_summary.to_string())

    print(f"초이스 요금제 가입 비율: {merged['is_choice_plan'].mean() * 100:.1f}%")
    high_price = merged["monthly_base_fee"] >= 80000
    job_high = pd.DataFrame({"occupation": merged["occupation"], "high": high_price}).groupby("occupation")["high"].mean().mul(100).round(1)
    print("\n[직업별 고가 요금제 가입률(%)]")
    print(job_high.sort_values(ascending=False).to_string())

    # 추천 테스트 사례
    print("\n[추천 테스트 케이스 수]")
    plan_info = plans.set_index("plan_id")
    cap = users["effective_data_gb"]
    unlimited = users["effective_data_unlimited"]
    fee = users["monthly_base_fee"]
    # 사용자별 콘텐츠 사용 비율
    content_by_user = (content_usage.groupby(["user_id", "content_category"])["data_usage_mb"].sum().unstack(fill_value=0))
    content_by_user["total_data"] = content_by_user.sum(axis=1)
    content_by_user["video_ratio"] = (content_by_user["video"] / content_by_user["total_data"])
    video_ratio = (users["user_id"].map(content_by_user["video_ratio"]).fillna(0))
    is_choice = users["current_plan_id"].map(plan_info["is_choice_plan"])

    case_a = (users["monthly_estimated_data_gb"] > 80) & (~unlimited) & (cap <= 30)
    case_b = (users["monthly_estimated_data_gb"] < 15) & (fee >= 80000)
    case_c = users["eligible_for_family_bundle"]
    case_d = ((video_ratio >= 0.25) & (users["monthly_estimated_data_gb"] >= 30) & (~is_choice))    
    case_e = users["benefit_low_use_seeded"] & users["current_plan_id"].map(plan_info["is_choice_plan"])
    
    print(f"Case A high usage + low-cap plan: {case_a.sum()}")
    print(f"Case B low usage + high-fee plan: {case_b.sum()}")
    print(f"Case C family exists + no bundle: {case_c.sum()}")
    print(f"Case D video-heavy + no Choice: {case_d.sum()}")
    print(f"Case E Choice benefit underuse seeded: {case_e.sum()}")


def save_csv(output_dir: Path, tables: Dict[str, pd.DataFrame]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    # 이전 스키마에서는 출력 테이블이었다. 현재는 내부 생성·검증 데이터이므로
    # 생성 출력 디렉터리를 덮어쓸 때 알려진 잔존 파일만 제거한다.
    for legacy_name in ("daily_usage", "family_relationships"):
        legacy_path = output_dir / f"{legacy_name}.csv"
        if legacy_path.exists():
            legacy_path.unlink()
            print(f"removed legacy output: {legacy_path}")
    for name, df in tables.items():
        path = output_dir / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"saved: {path} ({len(df):,} rows)")


def pseudonymize_key(value: object, domain: str, pseudonymization_key: str) -> object:
    """Return a stable, scoped HMAC key while preserving missing values.

    The default key is only suitable for this synthetic-data project. Real source
    data must supply a secret through ``--analysis-pseudonymization-key`` or
    ``KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY``.
    """
    if pd.isna(value) or value == "":
        return pd.NA
    message = f"{domain}:{value}".encode("utf-8")
    digest = hmac.new(
        pseudonymization_key.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()[:24].upper()
    prefixes = {
        "user": "AUSR",
        "family": "AFAM",
        "bundle_composition": "ABND",
    }
    return f"{prefixes[domain]}_{digest}"


def pseudonymize_series(series: pd.Series, domain: str, pseudonymization_key: str) -> pd.Series:
    return series.map(lambda value: pseudonymize_key(value, domain, pseudonymization_key)).astype("string")


def age_band(age: pd.Series) -> pd.Series:
    return pd.cut(
        pd.to_numeric(age, errors="coerce"),
        bins=[7, 12, 18, 24, 34, 49, 64, float("inf")],
        labels=["8-12", "13-18", "19-24", "25-34", "35-49", "50-64", "65+"],
        include_lowest=True,
    ).astype("string")


def month_cohort(date_values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(date_values, errors="coerce")
    return parsed.dt.to_period("M").astype("string")


def subscription_tenure_months(date_values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(date_values, errors="coerce")
    months = (REFERENCE_DATE.year - parsed.dt.year) * 12 + (REFERENCE_DATE.month - parsed.dt.month)
    return months.astype("Int64")


def create_analysis_tables(
    tables: Dict[str, pd.DataFrame], pseudonymization_key: str
) -> Dict[str, pd.DataFrame]:
    """Create the restricted, analysis-ready counterpart of generated raw CSVs.

    The output keeps stable join keys for users, families, and bundle
    compositions while removing names, exact ages, and exact subscription dates.
    Event-level usage dates are retained because they are needed for trend and
    recommendation-feature analysis.
    """
    analysis_tables = {name: df.copy() for name, df in tables.items()}
    users = tables["users"]

    analysis_tables["users"] = pd.DataFrame({
        "analysis_user_key": pseudonymize_series(users["user_id"], "user", pseudonymization_key),
        "age_band": age_band(users["age"]),
        "gender": users["gender"],
        "subscription_cohort": month_cohort(users["subscription_start_date"]),
        "tenure_months": subscription_tenure_months(users["subscription_start_date"]),
        "current_plan_id": users["current_plan_id"],
        "analysis_family_key": pseudonymize_series(users["family_id"], "family", pseudonymization_key),
    })

    families = tables["families"]
    analysis_tables["families"] = families.drop(columns=["family_id"]).copy()
    analysis_tables["families"].insert(
        0, "analysis_family_key", pseudonymize_series(families["family_id"], "family", pseudonymization_key)
    )

    compositions = tables["bundle_discount_compositions"]
    analysis_tables["bundle_discount_compositions"] = pd.DataFrame({
        "analysis_bundle_composition_key": pseudonymize_series(
            compositions["bundle_composition_id"], "bundle_composition", pseudonymization_key
        ),
        "analysis_family_key": pseudonymize_series(compositions["family_id"], "family", pseudonymization_key),
        "component_type": compositions["component_type"],
        "analysis_user_key": pseudonymize_series(compositions["user_id"], "user", pseudonymization_key),
        "component_role": compositions["component_role"],
        "status": compositions["status"],
        "start_month": month_cohort(compositions["start_date"]),
        "end_month": month_cohort(compositions["end_date"]),
    })

    user_discounts = tables["user_discounts"]
    analysis_tables["user_discounts"] = pd.DataFrame({
        "analysis_user_key": pseudonymize_series(user_discounts["user_id"], "user", pseudonymization_key),
        "analysis_bundle_composition_key": pseudonymize_series(
            user_discounts["bundle_composition_id"], "bundle_composition", pseudonymization_key
        ),
        "discount_id": user_discounts["discount_id"],
        "status": user_discounts["status"],
        "start_month": month_cohort(user_discounts["start_date"]),
        "end_month": month_cohort(user_discounts["end_date"]),
    })

    user_services = tables["user_services"]
    analysis_tables["user_services"] = pd.DataFrame({
        "analysis_user_key": pseudonymize_series(user_services["user_id"], "user", pseudonymization_key),
        "service_id": user_services["service_id"],
        "benefit_type": user_services["benefit_type"],
        "start_month": month_cohort(user_services["start_date"]),
    })

    content_usage = tables["content_usage"]
    analysis_tables["content_usage"] = pd.DataFrame({
        "analysis_user_key": pseudonymize_series(content_usage["user_id"], "user", pseudonymization_key),
        "usage_date": content_usage["usage_date"],
        "content_category": content_usage["content_category"],
        "content_detail": content_usage["content_detail"],
        "data_usage_mb": content_usage["data_usage_mb"],
    })
    return analysis_tables


def save_analysis_manifest(output_dir: Path, tables: Dict[str, pd.DataFrame]) -> None:
    manifest = {
        "dataset_type": "synthetic_pseudonymized_analysis_release",
        "reference_date": REFERENCE_DATE.date().isoformat(),
        "transformations": {
            "user_and_family_keys": "HMAC pseudonyms; source identifiers omitted",
            "name": "omitted",
            "age": "age_band",
            "subscription_start_date": "subscription_cohort and tenure_months",
            "lifecycle_dates": "start_date and end_date coarsened to YYYY-MM start_month and end_month",
            "row_identifiers": "content_usage_id, user_discount_id, and user_service_id omitted",
            "event_dates": "content_usage.usage_date retained at YYYY-MM-DD for usage analysis",
        },
        "tables": {name: {"row_count": len(df)} for name, df in tables.items()},
    }
    manifest_path = output_dir / "analysis_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {manifest_path}")


# -----------------------------------------------------------------------------
# 14. 전체 실행 흐름
# -----------------------------------------------------------------------------
def build_dataset(n_users: int = N_USERS, n_days: int = N_DAYS,
                  seed: int = SEED, suboptimal_ratio: float = SUBOPTIMAL_PLAN_RATIO,
                  output_dir: str | Path = DEFAULT_OUTPUT_DIR,
                  analysis_output_dir: str | Path = DEFAULT_ANALYSIS_OUTPUT_DIR,
                  analysis_pseudonymization_key: str = SYNTHETIC_ANALYSIS_KEY,
                  save: bool = True, save_analysis: bool = True) -> Dict[str, pd.DataFrame]:
    if n_users < 10:
        raise ValueError("n_users must be >= 10")
    if n_days < 1:
        raise ValueError("n_days must be >= 1")
    if not 0 <= suboptimal_ratio <= 0.8:
        raise ValueError("suboptimal_ratio must be between 0 and 0.8")

    np.random.seed(seed)
    random.seed(seed)
    load_reference_data()

    plans = create_plan_master()
    age_benefits = create_age_benefit_master()
    plan_age_benefits = create_plan_age_benefits(plans)
    discounts = create_discount_master()
    internet_bundle_rules = create_internet_bundle_discount_rules()
    premium_family_rules = create_premium_family_discount_rules()
    services = create_service_master()
    plan_benefits = create_plan_benefits(plans, services)

    families = generate_family_structures(n_users, np.random.default_rng(seed + 1))
    family_users, role_map = generate_family_members(families, seed + 2, start_user_seq=1)
    n_independent = n_users - len(family_users)
    independent_users = generate_independent_users(n_independent, seed + 3, start_user_seq=len(family_users) + 1)
    users = pd.concat([family_users, independent_users], ignore_index=True)
    relationships = generate_family_relationships(role_map)

    users = assign_occupations(users, seed + 4)
    users = assign_usage_profiles(users, seed + 5)
    users = assign_plans(users, plans, plan_age_benefits, seed + 6, suboptimal_ratio=suboptimal_ratio)
    users = assign_age_benefits(users, plans, age_benefits, plan_age_benefits)
    users = assign_subscription_tenure(users, seed + 10)
    users, user_services = assign_choice_benefits(users, plans, services, plan_benefits, seed + 7)
    families, users, bundle_compositions, user_discounts = assign_premium_family_bundles(
        families, users, plans, internet_bundle_rules, premium_family_rules, seed + 8
    )
    users = calculate_current_total_discount_amount(
        users,
        families,
        bundle_compositions,
        user_discounts,
        internet_bundle_rules,
        premium_family_rules,
    )
    users = calculate_family_features(users, families)

    daily_usage = generate_daily_usage(users, plans, n_days, seed + 11)
    content_usage = generate_content_usage(users, daily_usage, services, user_services, n_days, seed + 12)
    users = calculate_user_features(users, daily_usage, content_usage)

    # 검증과 요약에 사용하는 내부 사용자 컬럼
    requested_user_columns = [
        "user_id", "name", "age", "age_group", "gender",
        "occupation", "occupation_group",
        "subscription_start_date", "subscription_months",
        "current_plan_id",
        "current_age_benefit_id", "current_age_benefit_name",
        "age_bonus_data_gb", "age_bonus_shared_data_gb",
        "age_bonus_voice_minutes", "age_bonus_sms_count", "age_bonus_video_minutes",
        "age_benefit_safety_box", "effective_data_gb", "effective_data_unlimited",
        "effective_shared_data_gb",
        "family_id", "has_family", "has_family_bundle", "family_bundle_type",
        "monthly_base_fee", "current_total_discount_amount", "current_benefit_value",
        "avg_daily_data_mb", "monthly_estimated_data_gb", "top_content_category",
        "family_member_count", "kt_family_member_count", "eligible_for_family_bundle",
        "usage_profile", "content_affinity", "plan_spending_score",
        "is_suboptimal_seeded", "suboptimal_reason", "benefit_low_use_seeded", "family_role",
        "latent_daily_data_mb",
    ]
    users = users[requested_user_columns]

    # 최종 users.csv 출력 컬럼
    user_export_columns = [
        "user_id",
        "name",
        "age",
        "gender",
        "subscription_start_date",
        "current_plan_id",
        "family_id",
    ]

    users_export = users[user_export_columns].copy()
    run_all_validations(
        users, families, relationships, plans, services, plan_benefits,
        age_benefits, plan_age_benefits, discounts, bundle_compositions,
        user_discounts, user_services,
        internet_bundle_rules, premium_family_rules,
        daily_usage, content_usage,
    )
    print_summary(users, families, plans, user_discounts, user_services, services, content_usage)

    tables = {
        "users": users_export,
        "families": families[[
            "family_id", "has_bundle", "bundle_type", "has_kt_internet",
            "internet_product_group", "internet_contract_months", "internet_status", "bundle_discount_method",
            "total_discount_allocation_method",
            "internet_benefit_discount_id",
        ]],
        "bundle_discount_compositions": bundle_compositions,
        "plans": plans[[
            "plan_id", "plan_name", "plan_family", "plan_category", "monthly_fee",
            "data_limit_gb", "is_unlimited", "throttle_speed", "voice", "sms",
            "base_shared_data_gb", "is_rollover", "membership_tier", "choice_tier",
            "network_type", "device_discount_lines", "data_sharing_discount_lines",
            "family_bundle_eligible",
        ]],
        "age_benefits": age_benefits[[
            "age_benefit_id", "benefit_name", "min_age", "max_age", "includes_safety_box",
        ]],
        "plan_age_benefits": plan_age_benefits[[
            "plan_age_benefit_id", "plan_id", "age_benefit_id", "bonus_data_gb",
            "bonus_shared_data_gb", "bonus_voice_minutes", "bonus_sms_count",
            "bonus_video_minutes",
        ]],
        "additional_services": services[[
            "service_id", "service_name", "service_category", "normal_monthly_price",
        ]],
        "plan_benefits": plan_benefits[[
            "plan_benefit_id", "plan_id", "service_id", "benefit_type", "benefit_value",
            "is_selectable", "option_group", "selection_count",
        ]],
        "discounts": discounts,
        "internet_bundle_discount_rules": internet_bundle_rules,
        "premium_family_discount_rules": premium_family_rules,
        "user_discounts": user_discounts,
        "user_services": user_services,
        "content_usage": content_usage,
    }
    if save:
        raw_output_path = Path(output_dir)
        save_csv(raw_output_path, tables)
        if save_analysis:
            analysis_output_path = Path(analysis_output_dir)
            if raw_output_path.resolve() == analysis_output_path.resolve():
                raise ValueError("analysis_output_dir must be different from output_dir")
            analysis_tables = create_analysis_tables(tables, analysis_pseudonymization_key)
            save_csv(analysis_output_path, analysis_tables)
            save_analysis_manifest(analysis_output_path, analysis_tables)
    return tables


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate KT-like synthetic mobile customer data")
    p.add_argument("--n-users", type=int, default=N_USERS)
    p.add_argument("--n-days", type=int, default=N_DAYS)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--suboptimal-ratio", type=float, default=SUBOPTIMAL_PLAN_RATIO)
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    p.add_argument(
        "--analysis-output-dir", default=str(DEFAULT_ANALYSIS_OUTPUT_DIR),
        help="Directory for the pseudonymized analysis release CSVs",
    )
    p.add_argument(
        "--analysis-pseudonymization-key",
        default=os.environ.get("KT_ND_ANALYSIS_PSEUDONYMIZATION_KEY", SYNTHETIC_ANALYSIS_KEY),
        help="HMAC key for stable analysis keys; use an environment secret for real data",
    )
    p.add_argument(
        "--no-analysis-output", action="store_true",
        help="Write only generated raw CSVs",
    )
    p.add_argument("--no-save", action="store_true", help="Run/validate without writing CSV files")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    build_dataset(
        n_users=args.n_users,
        n_days=args.n_days,
        seed=args.seed,
        suboptimal_ratio=args.suboptimal_ratio,
        output_dir=args.output_dir,
        analysis_output_dir=args.analysis_output_dir,
        analysis_pseudonymization_key=args.analysis_pseudonymization_key,
        save=not args.no_save,
        save_analysis=not args.no_analysis_output,
    )


if __name__ == "__main__":
    main()
