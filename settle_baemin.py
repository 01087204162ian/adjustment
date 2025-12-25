# settle_baemin.py
"""
배민 배달 정산 보험료 계산 스크립트

[정산 기준]
- 배민 정산 기준시간: 06:00 ~ D+1 06:00
- DB 정산 기준시간: 00:00 ~ 24:00
- 경기도 일부 지역의 운행 중복시간은 배민에서 처리하지 않아 당사에서 처리

[처리 순서]
1. 운행시간(G열, H열)을 YYYY-MM-DD HH:MM:SS 형식으로 변경
2. 전체 운행시간(I열) = 종료시간(H열) - 시작시간(G열)
3. 상태정보(M열)이 '00'이 아닌 경우 정산 제외 (I열 값 삭제)
4. 보험사 기준영업일(O열) = 시작시간(G열)의 YYYY-MM-DD
5. 보험사 기사아이디(E열) + 보험사 기준영업일(O열)별 전체 운행시간 합산
6. 보험사 기사아이디 오름차순 정렬
7. 이전 종료시간이 다음 시작시간보다 이후인 운행건 확인
8. 일별 중복 운행시간 산출
9. 보험사 기사아이디 + 보험사 기준영업일별 전체 운행시간에서 중복 운행시간 차감
10. 운행시간(분)에 따른 보험료 산출 (담보별 요율 적용, 원단위 절사)
11. 보험사기준 영업일별 운행시간(분)과 보험료를 표로 산출

[담보별 요율]
- 대인1지원: 3.28
- 대인2: 4.34
- 대물: 3.68

사용법:
    python settle_baemin.py input.xlsx --out output.xlsx
"""
import argparse
import math
import sys
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import numpy as np

RATES = {
    "대인1지원": 3.28,
    "대인2": 4.34,
    "대물": 3.68,
}

# 상태정보(M열)이 '00'인 경우만 정산 대상
PAYABLE_STATUS = {"00"}

# 필수 컬럼명
REQUIRED_COLS = ["기사이이디", "시작시간", "종료시간", "담보", "보험사 정산 상태 정보"]


def to_kst_naive(ts: pd.Series) -> pd.Series:
    """
    시간 시리즈를 KST naive datetime으로 변환
    
    Args:
        ts: 시간 시리즈
        
    Returns:
        KST naive datetime 시리즈
    """
    ts = pd.to_datetime(ts, errors="coerce")
    # tz-aware면 Asia/Seoul로 변환 후 tz 제거
    if getattr(ts.dt, "tz", None) is not None:
        return ts.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    return ts


def merge_intervals(starts: List, ends: List) -> List[Tuple]:
    """
    겹치는 시간 구간을 병합
    
    Args:
        starts: 시작 시간 리스트
        ends: 종료 시간 리스트
        
    Returns:
        병합된 구간 리스트 [(start, end), ...]
    """
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


def validate_columns(df: pd.DataFrame) -> None:
    """
    필수 컬럼 존재 여부 확인
    
    Args:
        df: 데이터프레임
        
    Raises:
        ValueError: 필수 컬럼이 없을 경우
    """
    missing_cols = [col for col in REQUIRED_COLS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing_cols)}")


def process(input_xlsx: str, output_xlsx: str) -> None:
    """
    배민 배달 정산 보험료 계산 처리
    
    Args:
        input_xlsx: 입력 엑셀 파일 경로
        output_xlsx: 출력 엑셀 파일 경로
        
    Raises:
        FileNotFoundError: 입력 파일이 없을 경우
        ValueError: 데이터 검증 실패 시
    """
    # 입력 파일 존재 확인
    if not Path(input_xlsx).exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_xlsx}")
    
    # .crdownload 파일 체크 (Chrome 다운로드 중인 파일)
    if input_xlsx.endswith('.crdownload'):
        raise ValueError(
            f"다운로드 중인 파일입니다: {input_xlsx}\n"
            "Chrome에서 다운로드가 완료될 때까지 기다린 후, .xlsx 확장자로 변경된 파일을 사용하세요."
        )
    
    try:
        df = pd.read_excel(input_xlsx, engine="openpyxl")
    except Exception as e:
        error_msg = str(e)
        if "not a zip file" in error_msg.lower() or "bad zipfile" in error_msg.lower():
            raise ValueError(
                f"엑셀 파일 형식이 올바르지 않습니다: {input_xlsx}\n"
                "파일이 손상되었거나 다운로드가 완료되지 않았을 수 있습니다.\n"
                f"원본 오류: {error_msg}"
            )
        raise ValueError(f"엑셀 파일 읽기 실패: {error_msg}")
    
    if df.empty:
        raise ValueError("입력 파일이 비어있습니다.")
    
    # 필수 컬럼 검증
    validate_columns(df)
    
    # 컬럼명(업로드 파일 기준)
    col_driver = "기사이이디"
    col_start = "시작시간"
    col_end = "종료시간"
    col_cov = "담보"
    col_status = "보험사 정산 상태 정보"

    # 1) 운행시간(G열, H열)을 YYYY-MM-DD HH:MM:SS 형식으로 변경
    # 요구사항: 시작시간(G열)과 종료시간(H열)을 YYYY-MM-DD HH:MM:SS 형식으로 변환
    df["start_dt"] = to_kst_naive(df[col_start])
    df["end_dt"] = to_kst_naive(df[col_end])
    
    # 시간 파싱 실패 건 확인
    invalid_time = df["start_dt"].isna() | df["end_dt"].isna()
    if invalid_time.any():
        print(f"경고: 시간 파싱 실패 건수: {invalid_time.sum()}건")
    
    # 원본 컬럼이 있으면 형식 변환하여 업데이트
    if col_start in df.columns:
        df[col_start] = df["start_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    if col_end in df.columns:
        df[col_end] = df["end_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 2) 전체 운행시간(분단위)(I열) = 종료시간(H열) - 시작시간(G열)
    # 요구사항: 종료시간에서 시작시간을 뺀 값으로 변경
    dur_sec = (df["end_dt"] - df["start_dt"]).dt.total_seconds()
    df["calc_total_min"] = np.where(dur_sec.notna() & (dur_sec >= 0), np.ceil(dur_sec / 60.0), np.nan)
    
    # 원본 컬럼이 있으면 업데이트 (I열 = "전체 운행시간 (분단위)")
    if "전체 운행시간 (분단위)" in df.columns:
        df["전체 운행시간 (분단위)"] = df["calc_total_min"]
    
    # 음수 시간 확인
    negative_time = (dur_sec < 0) & dur_sec.notna()
    if negative_time.any():
        print(f"경고: 종료시간이 시작시간보다 빠른 건수: {negative_time.sum()}건")

    # 3) 상태정보(M열)이 '00'이 아닌 경우 정산 제외 (I열 값 삭제)
    # 요구사항: 상태정보가 '00'이 아닌 셀은 정산에서 제외해야 해서 전체 운행시간(I열) 값 삭제
    status = df[col_status].astype(str).str.strip()
    df["is_payable"] = status.isin(PAYABLE_STATUS)
    df.loc[~df["is_payable"], "calc_total_min"] = np.nan
    # 원본 컬럼도 업데이트
    if "전체 운행시간 (분단위)" in df.columns:
        df.loc[~df["is_payable"], "전체 운행시간 (분단위)"] = np.nan

    # 4) 보험사 기준영업일(O열): 시작시간(G열)의 YYYY-MM-DD
    # 요구사항: 보험사 기준영업일을 시작시간의 YYYY-MM-DD로 변경
    df["보험사기준영업일_calc"] = df["start_dt"].dt.strftime("%Y%m%d")
    df["보험사기준영업일_date"] = df["start_dt"].dt.strftime("%Y-%m-%d")
    # NaN 처리
    df["보험사기준영업일_calc"] = df["보험사기준영업일_calc"].fillna("")
    df["보험사기준영업일_date"] = df["보험사기준영업일_date"].fillna("")
    
    # 원본 컬럼이 있으면 업데이트 (O열 = "보험사기준영업일")
    if "보험사기준영업일" in df.columns:
        df["보험사기준영업일"] = df["보험사기준영업일_date"]

    # 5) 보험사 기사아이디(E열)의 보험사 기준영업일(O열)별 전체 운행시간(분단위) 합산
    # 6) 운행 중복시간 확인: 보험사 기사아이디 오름차순으로 정렬
    # 요구사항: 보험사 기사아이디 오름차순 정렬
    df_sorted = df.sort_values(
        [col_driver, "보험사기준영업일_calc", "start_dt", "end_dt"]
    ).reset_index(drop=True)

    # 7) 이전 종료시간(H열)이 바로 다음 시작시간(G열)보다 더 이후인 운행건 확인
    # 요구사항: 이전 종료시간이 다음 시작시간보다 이후인 경우 확인 (중복 확인)
    df_sorted["prev_end_dt"] = df_sorted.groupby([col_driver, "보험사기준영업일_calc"])["end_dt"].shift(1)
    df_sorted["is_overlap_with_prev"] = df_sorted["prev_end_dt"].notna() & (df_sorted["prev_end_dt"] > df_sorted["start_dt"])

    group_cols = [col_driver, "보험사기준영업일_calc"]
    summary_rows = []
    merged_rows = []

    for (driver, day), g in df_sorted.groupby(group_cols, sort=False):
        g_pay = g[g["is_payable"]].copy()
        if g_pay.empty:
            continue

        merged = merge_intervals(g_pay["start_dt"].tolist(), g_pay["end_dt"].tolist())
        
        if not merged:
            continue

        # 8) 일별 중복 운행시간 산출
        # 9) 보험사 기사아이디(E열)의 보험사 기준영업일(O열)별 전체 운행시간에서 중복 운행시간 차감
        total_sec = float(((g_pay["end_dt"] - g_pay["start_dt"]).dt.total_seconds()).sum())
        union_sec = sum((e - s).total_seconds() for s, e in merged)
        overlap_sec = max(0.0, total_sec - union_sec)

        summary_rows.append({
            col_driver: driver,
            "보험사기준영업일_calc": day,
            "보험사기준영업일_date": g_pay["보험사기준영업일_date"].iloc[0],
            "총운행시간_분(합산)": int(math.ceil(total_sec / 60.0)),
            "중복운행시간_분": int(math.ceil(overlap_sec / 60.0)),
            "정산운행시간_분(중복차감)": int(math.ceil(union_sec / 60.0)),
            "운행건수(정산대상)": int(len(g_pay)),
        })

        for seq, (s, e) in enumerate(merged, start=1):
            merged_rows.append({
                col_driver: driver,
                "보험사기준영업일_calc": day,
                "보험사기준영업일_date": g_pay["보험사기준영업일_date"].iloc[0],
                "merged_seq": seq,
                "merged_start": s,
                "merged_end": e,
                "merged_duration_min": int(math.ceil((e - s).total_seconds() / 60.0)),
            })

    daily_summary = pd.DataFrame(summary_rows)
    if not daily_summary.empty:
        daily_summary = daily_summary.sort_values([col_driver, "보험사기준영업일_calc"])
    
    merged_intervals_df = pd.DataFrame(merged_rows)
    if not merged_intervals_df.empty:
        merged_intervals_df = merged_intervals_df.sort_values([col_driver, "보험사기준영업일_calc", "merged_seq"])

    # 10) 보험료 산출
    # 요구사항: 총 분단위 시간에 각 담보별 보험료를 곱하고 원단위 절사
    # 그리고 원단위 절사된 금액을 모두 더함
    # 담보별 요율: 대인1지원 3.28, 대인2 4.34, 대물 3.68
    
    # 건별 보험료 계산 (상세 시트용)
    df_sorted["calc_total_min_filled"] = df_sorted["calc_total_min"].fillna(0)
    df_sorted["담보_요율"] = df_sorted[col_cov].map(RATES).fillna(0.0)
    df_sorted["보험료_계산"] = (
        np.where(
            df_sorted["is_payable"],
            np.floor(df_sorted["calc_total_min_filled"] * df_sorted["담보_요율"]).astype(int),
            0
        )
    )

    # 11) 보험사기준 영업일(O열)별 운행시간(분)과 보험료를 표로 산출
    # 요구사항: 일별로 정산운행시간(중복차감 후)에 담보별 요율을 곱하여 보험료 계산
    if not daily_summary.empty:
        # 일별 보험료 계산: 각 담보별로 계산 후 합산
        # 기사+영업일+담보별로 그룹화하여 보험료 계산
        prem_by_cov = []
        for (driver, day, cov), g in df_sorted[df_sorted["is_payable"]].groupby(
            [col_driver, "보험사기준영업일_calc", col_cov], sort=False
        ):
            total_min = g["calc_total_min"].sum()
            rate = RATES.get(cov, 0.0)
            premium = int(math.floor(total_min * rate))
            if premium > 0:
                prem_by_cov.append({
                    col_driver: driver,
                    "보험사기준영업일_calc": day,
                    col_cov: cov,
                    "premium": premium
                })
        
        # 담보별 보험료를 합산하여 일별 총 보험료 계산
        if prem_by_cov:
            prem_df = pd.DataFrame(prem_by_cov)
            prem_sum = prem_df.groupby([col_driver, "보험사기준영업일_calc"])["premium"].sum().reset_index()
            prem_sum.columns = [col_driver, "보험사기준영업일_calc", "보험료_계산"]
            daily_summary = daily_summary.merge(prem_sum, on=[col_driver, "보험사기준영업일_calc"], how="left")
            daily_summary["보험료_계산"] = daily_summary["보험료_계산"].fillna(0).astype(int)
        else:
            daily_summary["보험료_계산"] = 0

    # 결과 저장
    try:
        with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
            df_sorted.to_excel(writer, index=False, sheet_name="01_상세_보험료")
            if not daily_summary.empty:
                daily_summary.to_excel(writer, index=False, sheet_name="02_일자요약_보험료")
            if not merged_intervals_df.empty:
                merged_intervals_df.to_excel(writer, index=False, sheet_name="03_병합구간(검증)")
    except Exception as e:
        raise ValueError(f"엑셀 파일 저장 실패: {e}")


def main() -> None:
    """메인 함수"""
    ap = argparse.ArgumentParser(
        description="배민 배달 정산 보험료 계산",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input_xlsx", help="원본 배치데이터 xlsx")
    ap.add_argument("--out", default="정산_최종_결과.xlsx", help="출력 xlsx 파일명")
    args = ap.parse_args()
    
    try:
        process(args.input_xlsx, args.out)
        print(f"OK: {args.out}")
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"예상치 못한 오류: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
