"""입력 파일 구조 확인 스크립트"""
import pandas as pd

input_file = "driving_data_20251101_20251130.xlsx"

print("=" * 60)
print("입력 파일 구조 확인")
print("=" * 60)

try:
    # 전체 파일 읽기
    df = pd.read_excel(input_file, engine='openpyxl', header=0)
    
    print(f"\n총 행 수: {len(df):,}행")
    print(f"총 컬럼 수: {len(df.columns)}개")
    
    print(f"\n컬럼 목록 (처음 20개):")
    for i, col in enumerate(df.columns[:20], 1):
        print(f"  {i}. {col}")
    
    if len(df.columns) > 20:
        print(f"  ... (총 {len(df.columns)}개 컬럼)")
    
    # 필요한 열 확인 (D=3, F=5, G=6, H=7, I=8, L=11, N=13)
    col_indices = {
        'D': 3,   # 보험사 기사아이디
        'F': 5,   # 운행 시작시간
        'G': 6,   # 운행 종료시간
        'H': 7,   # 전체 운행시간(분)
        'I': 8,   # 담보
        'L': 11,  # 보험사 정산 상태
        'N': 13   # 보험사 기준영업일
    }
    
    print(f"\n필요한 열 확인:")
    for col_key, col_idx in col_indices.items():
        if col_idx < len(df.columns):
            col_name = df.columns[col_idx]
            sample_value = df.iloc[0, col_idx] if len(df) > 0 else "N/A"
            print(f"  열 {col_key} (인덱스 {col_idx}): '{col_name}'")
            print(f"    샘플 값: {sample_value}")
            print(f"    데이터 타입: {df.iloc[:, col_idx].dtype}")
            
            # NaN 개수 확인
            nan_count = df.iloc[:, col_idx].isna().sum()
            print(f"    NaN 개수: {nan_count:,} / {len(df):,}")
        else:
            print(f"  열 {col_key} (인덱스 {col_idx}): ❌ 존재하지 않음")
    
    print(f"\n샘플 데이터 (첫 3행, 필요한 열만):")
    sample_cols = [df.columns[i] for i in col_indices.values() if i < len(df.columns)]
    print(df[sample_cols].head(3).to_string())
    
    # F, G 열의 시간 형식 확인
    if col_indices['F'] < len(df.columns) and col_indices['G'] < len(df.columns):
        print(f"\n시간 데이터 형식 확인:")
        f_col = df.iloc[:, col_indices['F']]
        g_col = df.iloc[:, col_indices['G']]
        
        print(f"  F열 (시작시간) 데이터 타입: {f_col.dtype}")
        print(f"  G열 (종료시간) 데이터 타입: {g_col.dtype}")
        
        # 유효한 값 샘플
        valid_f = f_col.dropna()
        valid_g = g_col.dropna()
        
        if len(valid_f) > 0:
            print(f"  F열 샘플 값: {valid_f.iloc[0]} (타입: {type(valid_f.iloc[0])})")
        if len(valid_g) > 0:
            print(f"  G열 샘플 값: {valid_g.iloc[0]} (타입: {type(valid_g.iloc[0])})")
    
    # I열 담보 값 확인
    if col_indices['I'] < len(df.columns):
        i_col = df.iloc[:, col_indices['I']]
        print(f"\nI열 (담보) 값 분포:")
        value_counts = i_col.value_counts().head(10)
        print(value_counts)
        
except Exception as e:
    print(f"오류 발생: {e}")
    import traceback
    traceback.print_exc()

