"""
사륜 운행 데이터 → DB 정산 결과 변환 스크립트

[정산 기준]
- 배민 기준 영업일: 06:00 ~ D+1 06:00
- DB 기준 영업일: 00:00 ~ 24:00

[처리 순서]
1. 원본 데이터 로드
2. 정산 기준 시간 필터링 (배민 기준 영업일 매핑)
3. 운행 시간(분) 계산
4. 담보별 운행 시간 분리
5. 자차 포함/미포함 분리
6. 중복 운행 시간 계산 (자차 포함/미포함 분리)
7. 보험료 산출 (담보별 원단위 절사 후 합산)
8. 운행수 계산
9. 상태값 부여
10. 결과 엑셀 생성 (DB 사륜 포맷)

사용법:
    python settle_saryun.py input.xlsx --out output.xlsx
"""
import argparse
import math
import sys
from pathlib import Path
from typing import List, Tuple, Dict
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# 담보별 분당 보험료 (원/분)
RATES = {
    "대인1": 3.28,
    "대인1지원": 3.28,
    "대인2": 4.34,
    "대물": 3.68,
    "자차": 0.0,  # 자차는 보험료 없음
}

# 자차 담보명 (다양한 표현 가능)
SELF_CAR_KEYWORDS = ["자차", "자기부담금", "자기부담"]

# 필수 컬럼명
REQUIRED_COLS = [
    "보험사 운행 ID",
    "플랫폼 운행 ID",
    "기사이이디",  # 입력 파일의 실제 컬럼명
    "시작시간",
    "종료시간",
    "담보",
    "보험사기준영업일",
    "배민기준영업일",
    "보험사 정산 상태 정보",
]


def to_kst_naive(ts: pd.Series) -> pd.Series:
    """시간 시리즈를 KST naive datetime으로 변환"""
    ts = pd.to_datetime(ts, errors="coerce")
    if getattr(ts.dt, "tz", None) is not None:
        return ts.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    return ts


def calc_baemin_business_day(start_time: pd.Series) -> pd.Series:
    """
    배민 기준 영업일 계산 (06:00 ~ D+1 06:00)
    
    예: 2025-11-01 05:00 → 2025-10-31
        2025-11-01 07:00 → 2025-11-01
    """
    result = []
    for dt in start_time:
        if pd.isna(dt):
            result.append("")
            continue
        
        # 06:00 이전이면 전날
        if dt.hour < 6:
            business_day = (dt - timedelta(days=1)).date()
        else:
            business_day = dt.date()
        
        result.append(business_day.strftime("%Y-%m-%d"))
    
    return pd.Series(result, index=start_time.index)


def calc_db_business_day(start_time: pd.Series) -> pd.Series:
    """DB 기준 영업일 계산 (00:00 ~ 24:00)"""
    return pd.to_datetime(start_time).dt.strftime("%Y-%m-%d")


def is_self_car(coverage: str) -> bool:
    """담보가 자차인지 확인"""
    if pd.isna(coverage):
        return False
    coverage_str = str(coverage).strip()
    return any(keyword in coverage_str for keyword in SELF_CAR_KEYWORDS)


def merge_intervals(starts: List, ends: List) -> List[Tuple]:
    """겹치는 시간 구간을 병합"""
    intervals = [(s, e) for s, e in zip(starts, ends) if pd.notna(s) and pd.notna(e)]
    if not intervals:
        return []
    
    intervals.sort(key=lambda x: x[0])
    merged = []
    for s, e in intervals:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)
    return [tuple(m) for m in merged]


def calc_overlap_minutes(
    df: pd.DataFrame,
    group_cols: List[str],
    include_self_car: bool = True
) -> pd.Series:
    """
    중복 운행 시간 계산
    
    Args:
        df: 데이터프레임
        group_cols: 그룹화 컬럼 (예: ['기사이이디', '영업일'])
        include_self_car: 자차 포함 여부
    
    Returns:
        중복 시간(분) 시리즈
    """
    # 자차 필터링
    if include_self_car:
        df_filtered = df.copy()
    else:
        df_filtered = df[~df['is_self_car']].copy()
    
    if df_filtered.empty:
        return pd.Series(0, index=df.index)
    
    # 그룹별로 중복 시간 계산
    overlap_minutes = []
    
    for (group_key, group_df) in df_filtered.groupby(group_cols, sort=False):
        if len(group_df) <= 1:
            overlap_minutes.extend([0] * len(group_df))
            continue
        
        # 시간 구간 병합
        merged = merge_intervals(
            group_df['시작시간'].tolist(),
            group_df['종료시간'].tolist()
        )
        
        # 총 시간 계산
        total_sec = sum(
            (group_df['종료시간'] - group_df['시작시간']).dt.total_seconds()
        )
        union_sec = sum((e - s).total_seconds() for s, e in merged)
        overlap_sec = max(0.0, total_sec - union_sec)
        overlap_min = int(math.ceil(overlap_sec / 60.0))
        
        # 각 행에 중복 시간 할당
        overlap_minutes.extend([overlap_min] * len(group_df))
    
    # 원본 인덱스에 맞춰 반환
    result = pd.Series(0, index=df.index)
    result.loc[df_filtered.index] = overlap_minutes
    return result


def calc_premium(running_minutes: pd.Series, coverage: pd.Series) -> pd.Series:
    """
    보험료 계산 (담보별 원단위 절사 후 합산)
    
    중요: 각 담보별로 원단위 절사 후 합산
    """
    premium = pd.Series(0.0, index=running_minutes.index)
    
    for cov, rate in RATES.items():
        mask = coverage.str.contains(cov, na=False, case=False)
        if mask.any():
            # 분당 요율 × 운행시간(분) → 원단위 절사
            cov_premium = np.floor(running_minutes[mask] * rate).astype(int)
            premium.loc[mask] += cov_premium
    
    return premium.astype(int)


def map_status(status: pd.Series) -> pd.Series:
    """보험사 정산 상태 정보를 DB 상태값으로 매핑"""
    status_map = {
        "00": "정상",
        "01": "취소",
        "02": "제외",
        # 추가 매핑 필요 시 확장
    }
    
    return status.astype(str).str.strip().map(
        lambda x: status_map.get(x, x)
    )


def validate_columns(df: pd.DataFrame) -> None:
    """필수 컬럼 존재 여부 확인"""
    missing_cols = [col for col in REQUIRED_COLS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing_cols)}")


def process(input_xlsx: str, output_xlsx: str) -> None:
    """
    사륜 운행 데이터 → DB 정산 결과 변환
    
    Args:
        input_xlsx: 입력 엑셀 파일 경로
        output_xlsx: 출력 엑셀 파일 경로
    """
    # 입력 파일 확인
    if not Path(input_xlsx).exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_xlsx}")
    
    print(f"입력 파일 로드 중: {input_xlsx}")
    df = pd.read_excel(input_xlsx, engine="openpyxl")
    
    if df.empty:
        raise ValueError("입력 파일이 비어있습니다.")
    
    # 필수 컬럼 검증
    validate_columns(df)
    
    print("데이터 처리 시작...")
    
    # Step 1: 시간 형식 변환
    print("Step 1: 시간 형식 변환 중...")
    df["시작시간"] = to_kst_naive(df["시작시간"])
    df["종료시간"] = to_kst_naive(df["종료시간"])
    
    # Step 2: 영업일 계산
    print("Step 2: 영업일 계산 중...")
    df["배민기준영업일_calc"] = calc_baemin_business_day(df["시작시간"])
    df["DB기준영업일_calc"] = calc_db_business_day(df["시작시간"])
    
    # 원본 컬럼이 있으면 업데이트
    if "배민기준영업일" in df.columns:
        df["배민기준영업일"] = df["배민기준영업일_calc"]
    if "보험사기준영업일" in df.columns:
        df["보험사기준영업일"] = df["DB기준영업일_calc"]
    
    # Step 3: 운행 시간(분) 계산
    print("Step 3: 운행 시간 계산 중...")
    dur_sec = (df["종료시간"] - df["시작시간"]).dt.total_seconds()
    df["운행시간"] = np.where(
        dur_sec.notna() & (dur_sec >= 0),
        np.floor(dur_sec / 60.0).astype(int),  # 분 단위 절사
        0
    )
    
    # 원본 컬럼이 있으면 업데이트
    if "전체 운행시간 (분단위)" in df.columns:
        df["전체 운행시간 (분단위)"] = df["운행시간"]
    
    # Step 4: 자차 여부 확인
    print("Step 4: 자차 여부 확인 중...")
    df["is_self_car"] = df["담보"].apply(is_self_car)
    
    # Step 5: 중복 운행 시간 계산
    print("Step 5: 중복 운행 시간 계산 중...")
    # 입력 파일의 컬럼명에 맞춰 사용 (기사이이디)
    driver_col = "기사이이디" if "기사이이디" in df.columns else "기사아이디"
    group_cols = [driver_col, "배민기준영업일_calc"]
    
    # 자차 포함 중복 시간
    df["중복운행(분)_자차포함"] = calc_overlap_minutes(
        df, group_cols, include_self_car=True
    )
    
    # 자차 미포함 중복 시간
    df["중복운행(분)_자차미포함"] = calc_overlap_minutes(
        df, group_cols, include_self_car=False
    )
    
    # Step 6: 운행 시간 분리 (자차 포함/미포함)
    print("Step 6: 운행 시간 분리 중...")
    df["운행(분)_자차포함"] = df["운행시간"]
    df["운행(분)_자차미포함"] = np.where(
        df["is_self_car"],
        0,
        df["운행시간"]
    )
    
    # Step 7: 보험료 산출
    print("Step 7: 보험료 산출 중...")
    df["보험료"] = calc_premium(df["운행시간"], df["담보"])
    
    # 원본 컬럼이 있으면 업데이트
    if "총 보험료" in df.columns:
        df["총 보험료"] = df["보험료"]
    
    # Step 8: 운행수 계산
    print("Step 8: 운행수 계산 중...")
    # 보험사 운행 ID 기준으로 운행수 계산
    if "보험사 운행 ID" in df.columns:
        df["운행수"] = df.groupby("보험사 운행 ID")["보험사 운행 ID"].transform("count")
    else:
        df["운행수"] = 1
    
    # 원본 컬럼이 있으면 업데이트
    if "전체 운행횟수" in df.columns:
        df["전체 운행횟수"] = df["운행수"]
    
    # Step 9: 상태값 매핑
    print("Step 9: 상태값 매핑 중...")
    if "보험사 정산 상태 정보" in df.columns:
        df["상태"] = map_status(df["보험사 정산 상태 정보"])
    else:
        df["상태"] = "정상"
    
    # Step 10: 결과 컬럼 정리 및 재정렬
    print("Step 10: 결과 컬럼 정리 중...")
    
    # DB 사륜 포맷에 맞는 컬럼 순서
    output_cols = [
        "보험사 운행 ID",
        "플랫폼 운행 ID",
        "시작시간",
        "종료시간",
        "운행시간",
        "담보",
        "운행수",
        "보험료",
        "상태",
        "배민기준영업일_calc",
        "DB기준영업일_calc",
        "운행(분)_자차포함",
        "운행(분)_자차미포함",
        "중복운행(분)_자차포함",
        "중복운행(분)_자차미포함",
    ]
    
    # 존재하는 컬럼만 선택
    available_cols = [col for col in output_cols if col in df.columns]
    df_result = df[available_cols].copy()
    
    # 컬럼명 최종 정리
    df_result.rename(columns={
        "배민기준영업일_calc": "배민기준",
        "DB기준영업일_calc": "DB기준",
    }, inplace=True)
    
    # 날짜 컬럼 추가
    df_result["운행일"] = pd.to_datetime(df_result["시작시간"]).dt.strftime("%Y-%m-%d")
    
    # 최종 컬럼 순서 재정렬
    final_cols = [
        "보험사 운행 ID",
        "플랫폼 운행 ID",
        "시작시간",
        "종료시간",
        "운행시간",
        "담보",
        "운행수",
        "보험료",
        "상태",
        "배민기준",
        "DB기준",
        "운행일",
        "운행(분)_자차포함",
        "운행(분)_자차미포함",
        "중복운행(분)_자차포함",
        "중복운행(분)_자차미포함",
    ]
    
    final_cols = [col for col in final_cols if col in df_result.columns]
    df_result = df_result[final_cols]
    
    # Step 11: 일자별 집계 테이블 생성 (P~U)
    print("Step 11: 일자별 집계 테이블 생성 중...")
    
    # 운행일 기준으로 집계
    daily_summary = []
    
    # 운행일별로 그룹화
    for 운행일, group_df in df_result.groupby("운행일", sort=True):
        # 자차 포함 집계
        운행분_자차포함 = group_df["운행(분)_자차포함"].sum()
        중복운행분_자차포함 = group_df["중복운행(분)_자차포함"].sum()
        
        # 자차 미포함 집계
        운행분_자차미포함 = group_df["운행(분)_자차미포함"].sum()
        중복운행분_자차미포함 = group_df["중복운행(분)_자차미포함"].sum()
        
        daily_summary.append({
            "운행일": 운행일,
            "운행(분)_자차 포함": int(운행분_자차포함),
            "운행(분)_자차 미포함": int(운행분_자차미포함),
            "중복운행(분)_자차포함": int(중복운행분_자차포함),
            "중복운행(분)_자차미포함": int(중복운행분_자차미포함),
        })
    
    df_daily = pd.DataFrame(daily_summary)
    
    # 결과 저장 (같은 시트에 2개 테이블: A~N 운행건단위, P~U 일자별집계)
    print(f"결과 파일 저장 중: {output_xlsx}")
    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        # 시트 1: 운행(건) 단위 테이블 (A~N)
        df_result.to_excel(writer, index=False, sheet_name="DB_사륜_정산결과")
        
        # 같은 시트에 일자별 집계 테이블 추가 (P~U, startcol=15는 P열)
        if not df_daily.empty:
            # 헤더 행은 0번째 행 (df_result의 헤더와 같은 행)
            df_daily.to_excel(
                writer, 
                index=False, 
                sheet_name="DB_사륜_정산결과",
                startrow=0, 
                startcol=15  # P열부터 시작 (A=0, B=1, ..., P=15)
            )
    
    print("처리 완료!")
    print(f"총 {len(df_result):,}건 처리")
    print(f"총 보험료: {df_result['보험료'].sum():,}원")
    print(f"일자별 집계: {len(df_daily)}일")


def main() -> None:
    """메인 함수"""
    ap = argparse.ArgumentParser(
        description="사륜 운행 데이터 → DB 정산 결과 변환",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input_xlsx", help="원본 운행 데이터 xlsx")
    ap.add_argument("--out", default="DB_사륜_결과.xlsx", help="출력 xlsx 파일명")
    args = ap.parse_args()
    
    try:
        process(args.input_xlsx, args.out)
        print(f"OK: {args.out}")
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"예상치 못한 오류: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

