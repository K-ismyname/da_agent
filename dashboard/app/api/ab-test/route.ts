// A/B 테스트 데이터 프록시 — BigQuery 직접 호출 제거, FastAPI 경유로 통일
// [역할] main.py의 /ab-test를 중계. /ab-test 대시보드 페이지가 요약+일별
// 추이 차트를 그릴 때 호출한다.
// [왜 "BigQuery 직접 호출 제거"인가] 과거엔 프론트(dashboard/lib/bigquery.ts
// 같은 파일)에서 Next.js 서버가 BigQuery 클라이언트를 직접 갖고 있었던
// 것으로 보이는데, 그러면 BigQuery 인증 정보가 프론트/백엔드 두 곳에
// 중복 존재하게 된다. FastAPI 백엔드 하나로 데이터 접근을 일원화해
// 인증 정보 관리 지점을 하나로 줄인 것.
import { NextResponse } from 'next/server'
import { backendFetch } from '@/lib/backend'

export async function GET() {
  try {
    const res = await backendFetch('/ab-test')
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 })
  }
}
