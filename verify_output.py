#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
출력 파일 검증 스크립트
"""
import pandas as pd
import sys
import io
from pathlib import Path

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def verify_output(output_file: str = "정산_최종_결과.xlsx"):
    """출력 파일 검증"""
    print("=" * 60)
    print("Output File Verification")
    print("=" * 60)
    
    # 파일 존재 확인
    if not Path(output_file).exists():
        print(f"[ERROR] File not found: {output_file}")
        return False
    
    file_size = Path(output_file).stat().st_size
    print(f"[OK] File exists: {output_file}")
    print(f"  File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
    print()
    
    try:
        # 엑셀 파일 열기
        xls = pd.ExcelFile(output_file)
        print(f"[OK] Excel file opened successfully")
        print(f"  Sheet names: {xls.sheet_names}")
        print(f"  Total sheets: {len(xls.sheet_names)}")
        print()
        
        # 각 시트 검증
        for sheet_name in xls.sheet_names:
            print(f"[{sheet_name}] Sheet Verification")
            print("-" * 60)
            df = pd.read_excel(xls, sheet_name=sheet_name)
            print(f"  Total rows: {len(df):,}")
            print(f"  Total columns: {len(df.columns)}")
            print(f"  Column names: {list(df.columns)}")
            
            # 데이터 샘플 출력
            if len(df) > 0:
                print(f"\n  First 3 rows sample:")
                print(df.head(3).to_string())
                
                # 숫자 컬럼 합계 확인
                numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
                if len(numeric_cols) > 0:
                    print(f"\n  Numeric column statistics:")
                    for col in numeric_cols[:5]:  # 처음 5개만
                        if col in df.columns:
                            total = df[col].sum()
                            print(f"    {col}: Sum = {total:,.0f}")
            else:
                print("  [WARNING] No data found")
            print()
        
        # 특정 시트 상세 검증
        if "01_상세_보험료" in xls.sheet_names:
            df_detail = pd.read_excel(xls, sheet_name="01_상세_보험료")
            print("[01_상세_보험료] Detailed Verification")
            print("-" * 60)
            if "보험료_계산" in df_detail.columns:
                total_premium = df_detail["보험료_계산"].sum()
                print(f"  Total premium sum: {total_premium:,.0f} KRW")
            print()
        
        if "02_일자요약_보험료" in xls.sheet_names:
            df_summary = pd.read_excel(xls, sheet_name="02_일자요약_보험료")
            print("[02_일자요약_보험료] Detailed Verification")
            print("-" * 60)
            if "보험료_계산" in df_summary.columns:
                total_premium = df_summary["보험료_계산"].sum()
                print(f"  Total premium sum: {total_premium:,.0f} KRW")
            if "기사이이디" in df_summary.columns:
                unique_drivers = df_summary["기사이이디"].nunique()
                print(f"  Unique drivers: {unique_drivers:,}")
            print()
        
        print("=" * 60)
        print("[SUCCESS] Verification completed: File created successfully")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    output_file = sys.argv[1] if len(sys.argv) > 1 else "정산_최종_결과.xlsx"
    success = verify_output(output_file)
    sys.exit(0 if success else 1)

