"""
사륜 운행 데이터 → DB 정산 결과 변환 Streamlit 앱

사용법:
    streamlit run app.py
"""
import io
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# settle_saryun.py의 함수들을 import
try:
    from settle_saryun import (
        RATES,
        SELF_CAR_KEYWORDS,
        REQUIRED_COLS,
        to_kst_naive,
        calc_baemin_business_day,
        calc_db_business_day,
        is_self_car,
        merge_intervals,
        calc_overlap_minutes,
        calc_premium,
        map_status,
        validate_columns,
    )
except ImportError:
    st.error("settle_saryun.py 파일을 찾을 수 없습니다.")
    st.stop()

# 페이지 설정
st.set_page_config(
    page_title="사륜 정산 계산기",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 세션 상태 초기화
if "processed_data" not in st.session_state:
    st.session_state.processed_data = None
if "output_buffer" not in st.session_state:
    st.session_state.output_buffer = None


def process_data(df: pd.DataFrame) -> tuple:
    """
    사륜 운행 데이터 처리
    
    Args:
        df: 입력 데이터프레임
        
    Returns:
        (처리된 결과 데이터프레임, 일자별 집계 데이터프레임) 튜플
    """
    import math
    import numpy as np
    from datetime import timedelta
    
    # 필수 컬럼 검증
    validate_columns(df)
    
    # Step 1: 시간 형식 변환
    df["시작시간"] = to_kst_naive(df["시작시간"])
    df["종료시간"] = to_kst_naive(df["종료시간"])
    
    # Step 2: 영업일 계산
    df["배민기준영업일_calc"] = calc_baemin_business_day(df["시작시간"])
    df["DB기준영업일_calc"] = calc_db_business_day(df["시작시간"])
    
    # 원본 컬럼이 있으면 업데이트
    if "배민기준영업일" in df.columns:
        df["배민기준영업일"] = df["배민기준영업일_calc"]
    if "보험사기준영업일" in df.columns:
        df["보험사기준영업일"] = df["DB기준영업일_calc"]
    
    # Step 3: 운행 시간(분) 계산
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
    df["is_self_car"] = df["담보"].apply(is_self_car)
    
    # Step 5: 중복 운행 시간 계산
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
    df["운행(분)_자차포함"] = df["운행시간"]
    df["운행(분)_자차미포함"] = np.where(
        df["is_self_car"],
        0,
        df["운행시간"]
    )
    
    # Step 7: 보험료 산출
    df["보험료"] = calc_premium(df["운행시간"], df["담보"])
    
    # 원본 컬럼이 있으면 업데이트
    if "총 보험료" in df.columns:
        df["총 보험료"] = df["보험료"]
    
    # Step 8: 운행수 계산
    if "보험사 운행 ID" in df.columns:
        df["운행수"] = df.groupby("보험사 운행 ID")["보험사 운행 ID"].transform("count")
    else:
        df["운행수"] = 1
    
    # 원본 컬럼이 있으면 업데이트
    if "전체 운행횟수" in df.columns:
        df["전체 운행횟수"] = df["운행수"]
    
    # Step 9: 상태값 매핑
    if "보험사 정산 상태 정보" in df.columns:
        df["상태"] = map_status(df["보험사 정산 상태 정보"])
    else:
        df["상태"] = "정상"
    
    # Step 10: 결과 컬럼 정리 및 재정렬
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
    
    # 일자별 집계 테이블 생성 (P~U)
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
    
    return df_result, df_daily


def create_excel_output(df_result: pd.DataFrame, df_daily: pd.DataFrame = None) -> io.BytesIO:
    """엑셀 파일을 메모리에 생성 (2개 테이블: A~N 운행건단위, P~U 일자별집계)"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # 시트 1: 운행(건) 단위 테이블 (A~N)
        df_result.to_excel(writer, index=False, sheet_name="DB_사륜_정산결과")
        
        # 같은 시트에 일자별 집계 테이블 추가 (P~U, startcol=15는 P열)
        if df_daily is not None and not df_daily.empty:
            df_daily.to_excel(
                writer, 
                index=False, 
                sheet_name="DB_사륜_정산결과",
                startrow=0, 
                startcol=15  # P열부터 시작 (A=0, B=1, ..., P=15)
            )
    output.seek(0)
    return output


# 메인 UI
st.title("🚗 사륜 운행 데이터 → DB 정산 결과 변환")

# 사이드바
with st.sidebar:
    st.header("ℹ️ 안내")
    st.markdown("""
    ### 정산 기준
    - **배민 기준 영업일**: 06:00 ~ D+1 06:00
    - **DB 기준 영업일**: 00:00 ~ 24:00
    
    ### 담보별 분당 보험료
    - 대인1 / 대인1지원: 3.28원/분
    - 대인2: 4.34원/분
    - 대물: 3.68원/분
    - 자차: 0원/분 (보험료 없음)
    
    ### 주요 기능
    - 자차 포함/미포함 분리
    - 중복 운행 시간 계산
    - 담보별 보험료 산출 (원단위 절사 후 합산)
    - DB 정산 포맷 출력
    """)
    
    st.markdown("---")
    st.markdown("**필수 컬럼**")
    st.markdown("""
    - 보험사 운행 ID
    - 플랫폼 운행 ID
    - 기사이이디
    - 시작시간 / 종료시간
    - 담보
    - 보험사기준영업일
    - 배민기준영업일
    - 보험사 정산 상태 정보
    """)

# 파일 업로드
uploaded_file = st.file_uploader(
    "엑셀 파일 업로드 (.xlsx)",
    type=["xlsx"],
    help="사륜 운행 데이터가 포함된 엑셀 파일을 업로드하세요."
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
        try:
            validate_columns(df)
        except ValueError as e:
            st.error(f"❌ {e}")
            st.info("업로드된 파일의 컬럼 목록:")
            st.write(list(df.columns))
            st.stop()
        
        # 데이터 처리
        status_text.text("⚙️ 데이터 처리 중...")
        progress_bar.progress(30)
        
        df_result, df_daily = process_data(df)
        
        progress_bar.progress(90)
        status_text.text("📊 결과 생성 중...")
        
        # 결과를 세션 상태에 저장
        st.session_state.processed_data = df_result
        st.session_state.daily_data = df_daily
        
        # 엑셀 파일 생성
        output_buffer = create_excel_output(df_result, df_daily)
        st.session_state.output_buffer = output_buffer
        
        progress_bar.progress(100)
        status_text.text("✅ 처리 완료!")
        
        # 통계 정보 표시
        st.success("✅ 파일 처리가 완료되었습니다!")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("총 건수", f"{len(df_result):,}건")
        with col2:
            total_premium = df_result["보험료"].sum()
            st.metric("총 보험료", f"{total_premium:,}원")
        with col3:
            driver_col_result = "기사이이디" if "기사이이디" in df_result.columns else "기사아이디"
            if driver_col_result in df_result.columns:
                unique_drivers = df_result[driver_col_result].nunique()
                st.metric("고유 기사 수", f"{unique_drivers:,}명")
            else:
                st.metric("고유 기사 수", "N/A")
        with col4:
            total_running_min = df_result["운행시간"].sum()
            st.metric("총 운행시간", f"{total_running_min:,}분")
        
        # 결과 미리보기 탭
        tab1, tab2, tab3 = st.tabs(["📋 전체 데이터", "📊 통계", "📈 요약"])
        
        with tab1:
            st.subheader("DB 정산 결과 데이터")
            st.dataframe(
                df_result.head(1000),
                use_container_width=True,
                height=400
            )
            if len(df_result) > 1000:
                st.info(f"총 {len(df_result):,}건 중 상위 1,000건만 표시됩니다.")
        
        with tab2:
            st.subheader("통계 정보")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 담보별 통계")
                if "담보" in df_result.columns:
                    cov_stats = df_result.groupby("담보").agg({
                        "운행시간": "sum",
                        "보험료": "sum",
                        "운행수": "sum"
                    }).reset_index()
                    cov_stats.columns = ["담보", "총 운행시간(분)", "총 보험료(원)", "운행수"]
                    st.dataframe(cov_stats, use_container_width=True)
            
            with col2:
                st.markdown("### 상태별 통계")
                if "상태" in df_result.columns:
                    status_stats = df_result.groupby("상태").agg({
                        "운행시간": "sum",
                        "보험료": "sum",
                        "운행수": "sum"
                    }).reset_index()
                    status_stats.columns = ["상태", "총 운행시간(분)", "총 보험료(원)", "운행수"]
                    st.dataframe(status_stats, use_container_width=True)
            
            st.markdown("### 자차 포함/미포함 통계")
            col1, col2 = st.columns(2)
            with col1:
                total_with_self_car = df_result["운행(분)_자차포함"].sum()
                st.metric("자차 포함 운행시간", f"{total_with_self_car:,}분")
            with col2:
                total_without_self_car = df_result["운행(분)_자차미포함"].sum()
                st.metric("자차 미포함 운행시간", f"{total_without_self_car:,}분")
        
        with tab3:
            st.subheader("요약 정보")
            
            summary_data = {
                "항목": [
                    "총 건수",
                    "총 운행시간 (분)",
                    "총 보험료 (원)",
                    "자차 포함 운행시간 (분)",
                    "자차 미포함 운행시간 (분)",
                    "중복 운행시간 - 자차포함 (분)",
                    "중복 운행시간 - 자차미포함 (분)",
                ],
                "값": [
                    f"{len(df_result):,}",
                    f"{df_result['운행시간'].sum():,}",
                    f"{df_result['보험료'].sum():,}",
                    f"{df_result['운행(분)_자차포함'].sum():,}",
                    f"{df_result['운행(분)_자차미포함'].sum():,}",
                    f"{df_result['중복운행(분)_자차포함'].sum():,}",
                    f"{df_result['중복운행(분)_자차미포함'].sum():,}",
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
        
        # 다운로드 버튼
        st.markdown("---")
        st.subheader("📥 결과 다운로드")
        
        if st.session_state.output_buffer is not None:
            st.download_button(
                label="📥 DB 정산 결과 다운로드 (Excel)",
                data=st.session_state.output_buffer,
                file_name="DB_사륜_정산결과.xlsx",
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
        1. **파일 준비**: 사륜 운행 데이터가 포함된 엑셀 파일 준비
        2. **파일 업로드**: 위의 파일 업로드 영역에 파일을 드래그 앤 드롭하거나 클릭하여 선택
        3. **자동 처리**: 파일이 자동으로 처리되며 진행 상황이 표시됩니다
        4. **결과 확인**: 처리된 결과를 탭에서 미리 볼 수 있습니다
        5. **다운로드**: 결과 파일을 다운로드하여 사용하세요
        
        ### 출력 파일 구조
        - **DB_사륜_정산결과**: DB 정산 기준 결과 데이터
        - 자차 포함/미포함 분리
        - 중복 운행 시간 계산
        - 담보별 보험료 산출
        """)

