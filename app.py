"""
배민 배달 정산 보험료 계산 Streamlit 앱

사용법:
    streamlit run app.py
"""
import io
import math
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

# 기존 settle_baemin.py의 함수들을 import
try:
    from settle_baemin import (
        RATES,
        PAYABLE_STATUS,
        REQUIRED_COLS,
        merge_intervals,
        to_kst_naive,
        validate_columns,
    )
except ImportError:
    # settle_baemin.py가 없는 경우를 대비한 폴백
    import math
    from typing import List, Tuple
    
    RATES = {
        "대인1지원": 3.28,
        "대인2": 4.34,
        "대물": 3.68,
    }
    PAYABLE_STATUS = {"00"}
    REQUIRED_COLS = ["기사이이디", "시작시간", "종료시간", "담보", "보험사 정산 상태 정보"]
    
    def to_kst_naive(ts: pd.Series) -> pd.Series:
        ts = pd.to_datetime(ts, errors="coerce")
        if getattr(ts.dt, "tz", None) is not None:
            return ts.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
        return ts
    
    def merge_intervals(starts: List, ends: List) -> List[Tuple]:
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
        missing_cols = [col for col in REQUIRED_COLS if col not in df.columns]
        if missing_cols:
            raise ValueError(f"필수 컬럼이 없습니다: {', '.join(missing_cols)}")

# 페이지 설정
st.set_page_config(
    page_title="배민 정산 보험료 계산",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 세션 상태 초기화
if "processed_data" not in st.session_state:
    st.session_state.processed_data = None
if "output_buffer" not in st.session_state:
    st.session_state.output_buffer = None


def process_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    배민 배달 정산 보험료 계산 처리
    
    Args:
        df: 입력 데이터프레임
        
    Returns:
        (df_sorted, daily_summary, merged_intervals_df) 튜플
    """
    # 컬럼명(업로드 파일 기준)
    col_driver = "기사이이디"
    col_start = "시작시간"
    col_end = "종료시간"
    col_cov = "담보"
    col_status = "보험사 정산 상태 정보"

    # 1) 운행시간(G열, H열)을 YYYY-MM-DD HH:MM:SS 형식으로 변경
    df["start_dt"] = to_kst_naive(df[col_start])
    df["end_dt"] = to_kst_naive(df[col_end])
    
    # 원본 컬럼이 있으면 형식 변환하여 업데이트
    if col_start in df.columns:
        df[col_start] = df["start_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    if col_end in df.columns:
        df[col_end] = df["end_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")

    # 2) 전체 운행시간(분단위)(I열) = 종료시간(H열) - 시작시간(G열)
    dur_sec = (df["end_dt"] - df["start_dt"]).dt.total_seconds()
    df["calc_total_min"] = np.where(dur_sec.notna() & (dur_sec >= 0), np.ceil(dur_sec / 60.0), np.nan)
    
    if "전체 운행시간 (분단위)" in df.columns:
        df["전체 운행시간 (분단위)"] = df["calc_total_min"]

    # 3) 상태정보(M열)이 '00'이 아닌 경우 정산 제외
    status = df[col_status].astype(str).str.strip()
    df["is_payable"] = status.isin(PAYABLE_STATUS)
    df.loc[~df["is_payable"], "calc_total_min"] = np.nan
    if "전체 운행시간 (분단위)" in df.columns:
        df.loc[~df["is_payable"], "전체 운행시간 (분단위)"] = np.nan

    # 4) 보험사 기준영업일(O열): 시작시간(G열)의 YYYY-MM-DD
    df["보험사기준영업일_calc"] = df["start_dt"].dt.strftime("%Y%m%d")
    df["보험사기준영업일_date"] = df["start_dt"].dt.strftime("%Y-%m-%d")
    df["보험사기준영업일_calc"] = df["보험사기준영업일_calc"].fillna("")
    df["보험사기준영업일_date"] = df["보험사기준영업일_date"].fillna("")
    
    if "보험사기준영업일" in df.columns:
        df["보험사기준영업일"] = df["보험사기준영업일_date"]

    # 5-6) 정렬
    df_sorted = df.sort_values(
        [col_driver, "보험사기준영업일_calc", "start_dt", "end_dt"]
    ).reset_index(drop=True)

    # 7) 이전 종료시간이 다음 시작시간보다 이후인 운행건 확인
    df_sorted["prev_end_dt"] = df_sorted.groupby([col_driver, "보험사기준영업일_calc"])["end_dt"].shift(1)
    df_sorted["is_overlap_with_prev"] = df_sorted["prev_end_dt"].notna() & (df_sorted["prev_end_dt"] > df_sorted["start_dt"])

    group_cols = [col_driver, "보험사기준영업일_calc"]
    summary_rows = []
    merged_rows = []

    # 8-9) 중복 운행시간 계산
    for (driver, day), g in df_sorted.groupby(group_cols, sort=False):
        g_pay = g[g["is_payable"]].copy()
        if g_pay.empty:
            continue

        merged = merge_intervals(g_pay["start_dt"].tolist(), g_pay["end_dt"].tolist())
        
        if not merged:
            continue

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
    df_sorted["calc_total_min_filled"] = df_sorted["calc_total_min"].fillna(0)
    df_sorted["담보_요율"] = df_sorted[col_cov].map(RATES).fillna(0.0)
    df_sorted["보험료_계산"] = (
        np.where(
            df_sorted["is_payable"],
            np.floor(df_sorted["calc_total_min_filled"] * df_sorted["담보_요율"]).astype(int),
            0
        )
    )

    # 11) 일별 보험료 계산
    if not daily_summary.empty:
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
        
        if prem_by_cov:
            prem_df = pd.DataFrame(prem_by_cov)
            prem_sum = prem_df.groupby([col_driver, "보험사기준영업일_calc"])["premium"].sum().reset_index()
            prem_sum.columns = [col_driver, "보험사기준영업일_calc", "보험료_계산"]
            daily_summary = daily_summary.merge(prem_sum, on=[col_driver, "보험사기준영업일_calc"], how="left")
            daily_summary["보험료_계산"] = daily_summary["보험료_계산"].fillna(0).astype(int)
        else:
            daily_summary["보험료_계산"] = 0

    return df_sorted, daily_summary, merged_intervals_df


def create_excel_output(df_sorted: pd.DataFrame, daily_summary: pd.DataFrame, merged_intervals_df: pd.DataFrame) -> io.BytesIO:
    """엑셀 파일을 메모리에 생성"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_sorted.to_excel(writer, index=False, sheet_name="01_상세_보험료")
        if not daily_summary.empty:
            daily_summary.to_excel(writer, index=False, sheet_name="02_일자요약_보험료")
        if not merged_intervals_df.empty:
            merged_intervals_df.to_excel(writer, index=False, sheet_name="03_병합구간(검증)")
    output.seek(0)
    return output


# 메인 UI
st.title("📊 배민 배달 정산 보험료 계산")

# 사이드바
with st.sidebar:
    st.header("ℹ️ 안내")
    st.markdown("""
    ### 정산 기준
    - 배민 정산 기준시간: 06:00 ~ D+1 06:00
    - DB 정산 기준시간: 00:00 ~ 24:00
    
    ### 담보별 요율
    - 대인1지원: 3.28원/분
    - 대인2: 4.34원/분
    - 대물: 3.68원/분
    
    ### 필수 컬럼
    - 기사이이디
    - 시작시간
    - 종료시간
    - 담보
    - 보험사 정산 상태 정보
    """)
    
    st.markdown("---")
    st.markdown("**상태정보 '00'인 경우만 정산 대상**")

# 파일 업로드
uploaded_file = st.file_uploader(
    "엑셀 파일 업로드 (.xlsx)",
    type=["xlsx"],
    help="배민 배달 데이터가 포함된 엑셀 파일을 업로드하세요."
)

if uploaded_file is not None:
    # .crdownload 파일 체크
    if uploaded_file.name.endswith('.crdownload'):
        st.error("❌ 다운로드 중인 파일입니다. 다운로드가 완료될 때까지 기다린 후 다시 시도하세요.")
        st.stop()
    
    # 진행 상황 표시
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # 파일 읽기
        status_text.text("📖 파일 읽는 중...")
        progress_bar.progress(10)
        
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        
        if df.empty:
            st.error("❌ 입력 파일이 비어있습니다.")
            st.stop()
        
        # 필수 컬럼 검증
        status_text.text("✅ 필수 컬럼 검증 중...")
        progress_bar.progress(20)
        validate_columns(df)
        
        # 데이터 처리
        status_text.text("⚙️ 데이터 처리 중...")
        progress_bar.progress(30)
        
        df_sorted, daily_summary, merged_intervals_df = process_data(df)
        
        progress_bar.progress(80)
        status_text.text("📊 결과 생성 중...")
        
        # 결과를 세션 상태에 저장
        st.session_state.processed_data = {
            "df_sorted": df_sorted,
            "daily_summary": daily_summary,
            "merged_intervals_df": merged_intervals_df,
        }
        
        # 엑셀 파일 생성
        output_buffer = create_excel_output(df_sorted, daily_summary, merged_intervals_df)
        st.session_state.output_buffer = output_buffer
        
        progress_bar.progress(100)
        status_text.text("✅ 처리 완료!")
        
        # 통계 정보 표시
        st.success("✅ 파일 처리가 완료되었습니다!")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("총 건수", f"{len(df_sorted):,}건")
        with col2:
            st.metric("정산 대상 건수", f"{df_sorted['is_payable'].sum():,}건")
        with col3:
            if not daily_summary.empty:
                st.metric("고유 기사 수", f"{daily_summary['기사이이디'].nunique():,}명")
            else:
                st.metric("고유 기사 수", "0명")
        with col4:
            if not daily_summary.empty:
                total_premium = daily_summary["보험료_계산"].sum()
                st.metric("총 보험료", f"{total_premium:,}원")
            else:
                st.metric("총 보험료", "0원")
        
        # 결과 미리보기 탭
        tab1, tab2, tab3, tab4 = st.tabs(["📋 상세 보험료", "📅 일자별 요약", "🔍 병합 구간", "📊 통계"])
        
        with tab1:
            st.subheader("01_상세_보험료")
            st.dataframe(
                df_sorted.head(1000),
                use_container_width=True,
                height=400
            )
            if len(df_sorted) > 1000:
                st.info(f"총 {len(df_sorted):,}건 중 상위 1,000건만 표시됩니다.")
        
        with tab2:
            st.subheader("02_일자요약_보험료")
            if not daily_summary.empty:
                st.dataframe(
                    daily_summary,
                    use_container_width=True,
                    height=400
                )
                
                # 차트
                if len(daily_summary) > 0:
                    st.subheader("일별 보험료 추이")
                    chart_data = daily_summary.groupby("보험사기준영업일_date")["보험료_계산"].sum().reset_index()
                    chart_data.columns = ["날짜", "보험료"]
                    st.line_chart(chart_data.set_index("날짜"))
            else:
                st.info("일자별 요약 데이터가 없습니다.")
        
        with tab3:
            st.subheader("03_병합구간(검증)")
            if not merged_intervals_df.empty:
                st.dataframe(
                    merged_intervals_df.head(500),
                    use_container_width=True,
                    height=400
                )
                if len(merged_intervals_df) > 500:
                    st.info(f"총 {len(merged_intervals_df):,}건 중 상위 500건만 표시됩니다.")
            else:
                st.info("병합 구간 데이터가 없습니다.")
        
        with tab4:
            st.subheader("통계 정보")
            
            if not daily_summary.empty:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### 일별 통계")
                    daily_stats = daily_summary.groupby("보험사기준영업일_date").agg({
                        "기사이이디": "nunique",
                        "정산운행시간_분(중복차감)": "sum",
                        "보험료_계산": "sum",
                        "운행건수(정산대상)": "sum"
                    }).reset_index()
                    daily_stats.columns = ["날짜", "기사 수", "운행시간(분)", "보험료(원)", "운행건수"]
                    st.dataframe(daily_stats, use_container_width=True)
                
                with col2:
                    st.markdown("### 담보별 통계")
                    if "담보" in df_sorted.columns:
                        cov_stats = df_sorted[df_sorted["is_payable"]].groupby("담보").agg({
                            "calc_total_min": "sum",
                            "보험료_계산": "sum"
                        }).reset_index()
                        cov_stats.columns = ["담보", "총 운행시간(분)", "총 보험료(원)"]
                        st.dataframe(cov_stats, use_container_width=True)
        
        # 다운로드 버튼
        st.markdown("---")
        st.subheader("📥 결과 다운로드")
        
        if st.session_state.output_buffer is not None:
            st.download_button(
                label="📥 정산 결과 다운로드 (Excel)",
                data=st.session_state.output_buffer,
                file_name="정산_최종_결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary"
            )
    
    except ValueError as e:
        st.error(f"❌ 오류: {e}")
        progress_bar.empty()
        status_text.empty()
    except Exception as e:
        st.error(f"❌ 예상치 못한 오류: {e}")
        progress_bar.empty()
        status_text.empty()
        st.exception(e)
else:
    st.info("👆 위에서 엑셀 파일을 업로드하세요.")
    
    # 사용 예시
    with st.expander("📖 사용 방법"):
        st.markdown("""
        1. **파일 준비**: 배민 배달 데이터가 포함된 엑셀 파일 준비
        2. **파일 업로드**: 위의 파일 업로드 영역에 파일을 드래그 앤 드롭하거나 클릭하여 선택
        3. **자동 처리**: 파일이 자동으로 처리되며 진행 상황이 표시됩니다
        4. **결과 확인**: 처리된 결과를 탭에서 미리 볼 수 있습니다
        5. **다운로드**: 결과 파일을 다운로드하여 사용하세요
        
        ### 출력 파일 구조
        - **01_상세_보험료**: 건별 상세 보험료 계산 결과
        - **02_일자요약_보험료**: 기사별 일자별 요약 (중복 시간 차감)
        - **03_병합구간(검증)**: 병합된 운행 구간 정보
        """)

