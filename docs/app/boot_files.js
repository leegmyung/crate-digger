// 첫 진입(db.js bootstrapData)에 받을 파일 고르기 — 순수 함수, tests/js/boot_files.test.mjs

/**
 * signals 를 Parquet 판(signals.parquet, 약 0.33MB)으로 읽어도 되나 — CSV(약 4MB) 대신.
 * scripts/update_meta_extras.py 가 CSV 보다 오래되지 않고 행 수가 같은 Parquet 만 extras_rows 에 적는다.
 * 여기서도 meta.rows.signals(export_lab_data 가 적은 행 수)와 한 번 더 맞춰 본다 — 다르면 CSV.
 * @param {{ rows?: {signals?: number}, extras_rows?: Record<string, number|boolean> } | null} meta
 */
export function signalsParquetOk(meta) {
  const want = Number(meta?.rows?.signals);
  const have = meta?.extras_rows?.['signals.parquet'];
  return Number.isFinite(want) && want > 0 && typeof have === 'number' && have === want;
}
