# app.py
import io
import numpy as np
import pandas as pd
import streamlit as st

ST_RATE_JACHA = 11.6
ST_RATE_NOJACHA = 9.02

st.set_page_config(page_title="시간제보험 정산", layout="wide")
st.title("시간제보험(사륜차) 운행 데이터 정산")

st.markdown(
    """
- 입력: Excel(xlsx)
- 규칙(확정): I열 담보 = `jacha(자차포함)`, `nojacha(자차미포함)` / **L열 상태 `'정상'`만 정산**
- 출력: `정산_요약(일자)`, `중복_상세(기사)`, `오류_리포트`
"""
)

rounding_mode = st.selectbox(
    "보험료 원 단위 처리",
    options=["반올림(round)", "버림(floor)", "올림(ceil)"],
    index=0,
)

uploaded = st.file_uploader("엑셀 파일 업로드 (.xlsx)", type=["xlsx"])


def make_datetimes_excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Excel은 tz-aware datetime을 저장 못하므로 tz 정보를 제거(naive로 변환)"""
    df2 = df.copy()
    for c in df2.columns:
        if pd.api.types.is_datetime64tz_dtype(df2[c]):
            df2[c] = df2[c].dt.tz_localize(None)
    return df2


def _to_dt(series: pd.Series, col_name: str, errors: list) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    bad = dt.isna() & series.notna() & (series.astype(str).str.strip() != "")
    if bad.any():
        for idx in series[bad].index[:2000]:
            errors.append(
                {
                    "row_index": int(idx) + 2,
                    "type": "time_parse_fail",
                    "col": col_name,
                    "value": str(series.loc[idx]),
                }
            )
    return dt


def _ceil_minutes(delta_seconds: pd.Series) -> pd.Series:
    """
    ceil(seconds/60) with NaN preserved (SAFE):
    pd.NA(NAType) -> NaN으로 강제 변환 후 numpy 처리
    """
    sec = pd.to_numeric(delta_seconds, errors="coerce").to_numpy(dtype="float64")
    out = np.full(sec.shape, np.nan, dtype="float64")
    mask = ~np.isnan(sec)
    out[mask] = np.ceil(sec[mask] / 60.0)
    return pd.Series(out, index=delta_seconds.index).astype("Int64")


def _apply_rounding_vectorized(series: pd.Series) -> pd.Series:
    """
    Vectorized rounding (SAFE):
    pd.NA(NAType) -> NaN으로 강제 변환 후 numpy 처리
    """
    arr = pd.to_numeric(series, errors="coerce").to_numpy(dtype="float64")
    out = np.zeros(arr.shape, dtype="int64")
    mask = ~np.isnan(arr)

    if rounding_mode.startswith("반올림"):
        out[mask] = np.rint(arr[mask]).astype("int64")
    elif rounding_mode.startswith("버림"):
        out[mask] = np.floor(arr[mask]).astype("int64")
    else:  # 올림
        out[mask] = np.ceil(arr[mask]).astype("int64")

    return pd.Series(out, index=series.index)


def process(df: pd.DataFrame, status=None):
    if status:
        status.update(label="1) 파일 읽기 완료", state="running")

    errors = []

    needed_positions = {"D": 3, "F": 5, "G": 6, "H": 7, "I": 8, "L": 11, "N": 13}
    max_pos = max(needed_positions.values())
    if df.shape[1] <= max_pos:
        raise ValueError(
            f"필요 열 위치까지 컬럼이 없습니다. 현재 컬럼 수={df.shape[1]}, 필요 최소={max_pos+1}"
        )

    col_D = df.columns[needed_positions["D"]]
    col_F = df.columns[needed_positions["F"]]
    col_G = df.columns[needed_positions["G"]]
    col_H = df.columns[needed_positions["H"]]
    col_I = df.columns[needed_positions["I"]]
    col_L = df.columns[needed_positions["L"]]
    col_N = df.columns[needed_positions["N"]]

    # Parse times
    if status:
        status.update(label="2) 시간 파싱 중...", state="running")
    df["_start_dt"] = _to_dt(df[col_F], "F(start)", errors)
    df["_end_dt"] = _to_dt(df[col_G], "G(end)", errors)

    # End < start
    bad_order = (
        df["_start_dt"].notna()
        & df["_end_dt"].notna()
        & (df["_end_dt"] < df["_start_dt"])
    )
    if bad_order.any():
        for idx in df[bad_order].index[:2000]:
            errors.append(
                {
                    "row_index": int(idx) + 2,
                    "type": "end_before_start",
                    "col": "F/G",
                    "value": f"start={df.loc[idx,'_start_dt']}, end={df.loc[idx,'_end_dt']}",
                }
            )

    # duration seconds
    df["_dur_sec"] = (df["_end_dt"] - df["_start_dt"]).dt.total_seconds()
    df.loc[bad_order, "_dur_sec"] = np.nan

    # H recompute: ceil minutes
    if status:
        status.update(label="3) 운행시간(분) 계산 중...", state="running")
    df[col_H] = _ceil_minutes(df["_dur_sec"])

    # L status normalize - '정상'만 정산 포함
    if status:
        status.update(label="4) 정산 제외 처리 중...", state="running")
    status_str = df[col_L].fillna("").astype(str).str.strip()
    include_mask = status_str == "정상"
    exclude = ~include_mask
    df.loc[exclude, col_H] = pd.NA

    # N = date(start)
    df[col_N] = df["_start_dt"].dt.strftime("%Y-%m-%d")

    # I 담보 normalize (공백류 제거까지 안전하게)
    df["_cover"] = (
        df[col_I]
        .fillna("")
        .astype(str)
        .str.lower()
        .str.replace(r"\s+", "", regex=True)
    )
    valid_cover = df["_cover"].isin(["jacha", "nojacha"])
    if (~valid_cover & df[col_I].notna()).any():
        for idx in df[(~valid_cover) & df[col_I].notna()].index[:2000]:
            errors.append(
                {
                    "row_index": int(idx) + 2,
                    "type": "invalid_cover",
                    "col": "I(담보)",
                    "value": str(df.loc[idx, col_I]),
                }
            )
    df.loc[~valid_cover, "_cover"] = pd.NA

    # Only rows with valid H and valid cover participate in summaries
    df["_ok"] = (
        df[col_H].notna()
        & df["_cover"].notna()
        & df[col_N].notna()
        & df[col_D].notna()
    )

    # -------- Overlap detection (per D+N) --------
    if status:
        status.update(label="5) 중복 운행 계산 중...", state="running")
    work = df[df["_ok"]].copy()
    work["_driver"] = work[col_D].astype(str)
    work["_date"] = work[col_N].astype(str)

    work = work.sort_values(by=["_driver", "_date", "_start_dt"], kind="mergesort")

    # prev end/start
    work["_prev_end"] = work.groupby(["_driver", "_date"])["_end_dt"].shift(1)
    work["_prev_start"] = work.groupby(["_driver", "_date"])["_start_dt"].shift(1)

    overlap_mask = work["_prev_end"].notna() & (work["_prev_end"] > work["_start_dt"])
    work["_overlap_sec"] = np.nan
    work.loc[overlap_mask, "_overlap_sec"] = (
        work.loc[overlap_mask, "_prev_end"] - work.loc[overlap_mask, "_start_dt"]
    ).dt.total_seconds()

    work["_overlap_min"] = _ceil_minutes(work["_overlap_sec"])

    # Assign overlap to "next row's cover" (this row's cover)
    work["_overlap_jacha"] = 0
    work["_overlap_nojacha"] = 0
    jmask = overlap_mask & (work["_cover"] == "jacha")
    nmask = overlap_mask & (work["_cover"] == "nojacha")
    work.loc[jmask, "_overlap_jacha"] = work.loc[jmask, "_overlap_min"].fillna(0).astype(int)
    work.loc[nmask, "_overlap_nojacha"] = work.loc[nmask, "_overlap_min"].fillna(0).astype(int)

    # Overlap detail sheet
    overlap_detail = work.loc[
        overlap_mask,
        ["_driver", "_date", "_prev_start", "_prev_end", "_start_dt", "_end_dt", "_cover", "_overlap_min"],
    ].rename(
        columns={
            "_driver": "기사ID(D)",
            "_date": "기준영업일(N)",
            "_prev_start": "이전 시작",
            "_prev_end": "이전 종료",
            "_start_dt": "다음 시작",
            "_end_dt": "다음 종료",
            "_cover": "다음 담보(I)",
            "_overlap_min": "중복시간(분)",
        }
    )

    # Daily sums for run minutes by cover
    work["_run_jacha"] = 0
    work["_run_nojacha"] = 0
    work.loc[work["_cover"] == "jacha", "_run_jacha"] = work.loc[work["_cover"] == "jacha", col_H].astype(int)
    work.loc[work["_cover"] == "nojacha", "_run_nojacha"] = work.loc[work["_cover"] == "nojacha", col_H].astype(int)

    daily = (
        work.groupby(["_date"], as_index=False)
        .agg(
            **{
                "운행(분)_자차포함": ("_run_jacha", "sum"),
                "운행(분)_자차미포함": ("_run_nojacha", "sum"),
                "중복운행(분)_자차포함": ("_overlap_jacha", "sum"),
                "중복운행(분)_자차미포함": ("_overlap_nojacha", "sum"),
            }
        )
        .rename(columns={"_date": "운행일"})
    )

    daily["정산 운행(분)_자차포함"] = daily["운행(분)_자차포함"] - daily["중복운행(분)_자차포함"]
    daily["정산 운행(분)_자차미포함"] = daily["운행(분)_자차미포함"] - daily["중복운행(분)_자차미포함"]

    # 보험료
    daily["분당단가_자차포함"] = ST_RATE_JACHA
    daily["분당단가_자차미포함"] = ST_RATE_NOJACHA

    if status:
        status.update(label="6) 보험료 산출 중...", state="running")
    daily["보험료_자차포함"] = _apply_rounding_vectorized(daily["정산 운행(분)_자차포함"] * ST_RATE_JACHA)
    daily["보험료_자차미포함"] = _apply_rounding_vectorized(daily["정산 운행(분)_자차미포함"] * ST_RATE_NOJACHA)
    daily["일자 총보험료"] = daily["보험료_자차포함"] + daily["보험료_자차미포함"]

    # Error report
    err_df = pd.DataFrame(errors)
    if err_df.empty:
        err_df = pd.DataFrame([{"type": "none", "message": "오류 없음"}])

    # Debug
    debug_info = {
        "총_행수": len(df),
        "start_dt_notna": int(df["_start_dt"].notna().sum()),
        "end_dt_notna": int(df["_end_dt"].notna().sum()),
        "H_notna": int(df[col_H].notna().sum()),
        "cover_valid": int(df["_cover"].notna().sum()),
        "N_notna": int(df[col_N].notna().sum()),
        "ok_rows": int(df["_ok"].sum()),
        "정산_포함_행수(L=정상)": int(include_mask.sum()),
        "정산_제외_행수": int(exclude.sum()),
    }

    return daily, overlap_detail, err_df, debug_info, status_str


if uploaded:
    try:
        in_bytes = uploaded.read()
        df0 = pd.read_excel(io.BytesIO(in_bytes), engine="openpyxl")
        st.write(f"로드 완료: {df0.shape[0]:,} rows × {df0.shape[1]:,} cols")

        if st.button("정산 실행(요약/중복/오류 생성)", type="primary"):
            with st.status("정산 처리 중...", expanded=True) as status:
                status.update(label="처리 시작...", state="running")
                daily, overlap_detail, err_df, debug_info, status_str = process(df0, status=status)
                status.update(label="결과 생성 완료!", state="complete")

            st.subheader("🔍 디버그 정보")
            col1, col2 = st.columns(2)
            with col1:
                st.write("**DEBUG COUNTS:**")
                st.json(debug_info)
            with col2:
                st.write("**L열 상태값 분포 (상위 10):**")
                st.dataframe(status_str.value_counts(dropna=False).head(10))

            st.subheader("정산_요약(일자)")
            st.dataframe(daily, use_container_width=True)

            st.subheader("중복_상세(기사) (상위 200건)")
            st.dataframe(overlap_detail.head(200), use_container_width=True)

            st.subheader("오류_리포트 (상위 200건)")
            st.dataframe(err_df.head(200), use_container_width=True)

            out = io.BytesIO()

            # Excel 저장 전 timezone 제거 (핵심 패치)
            daily_x = make_datetimes_excel_safe(daily)
            overlap_x = make_datetimes_excel_safe(overlap_detail)
            err_x = make_datetimes_excel_safe(err_df)

            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                daily_x.to_excel(writer, index=False, sheet_name="정산_요약(일자)")
                overlap_x.to_excel(writer, index=False, sheet_name="중복_상세(기사)")
                err_x.to_excel(writer, index=False, sheet_name="오류_리포트")
            out.seek(0)

            st.download_button(
                "결과 엑셀 다운로드",
                data=out,
                file_name="정산_결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(f"처리 중 오류: {e}")
else:
    st.info("좌측에서 엑셀 파일을 업로드하세요.")
