// BigQuery 마트 데이터를 직접 반환하는 프록시 — LLM 파이프라인 없이 차트용
// [역할] main.py의 /data(LLM 미경유, 즉시 응답)를 그대로 중계. /analyze와
// 달리 maxDuration을 늘릴 필요가 없다 — BigQuery 조회만 하므로 기본
// 타임아웃 내에 항상 끝난다. 대시보드 첫 진입 시 이 라우트로 초기 차트를 그린다.
import { NextResponse } from 'next/server'
import { backendFetch } from '@/lib/backend'

export async function GET() {
  try {
    const res = await backendFetch('/data')
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 500 })
  }
}
