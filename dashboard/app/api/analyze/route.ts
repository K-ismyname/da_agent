// [역할] CLAUDE.md 아키텍처의 "Next.js (프론트 + API proxy)" 계층 중
// /analyze 엔드포인트. 브라우저는 이 라우트만 호출하고, 실제 FastAPI 백엔드
// 주소나 인증 시크릿은 서버 사이드(이 파일)에만 존재한다 — 브라우저에
// 백엔드 URL·시크릿을 노출하지 않기 위한 프록시 패턴.
import { NextResponse } from 'next/server'
import { backendFetch } from '@/lib/backend'

// LLM 파이프라인이 2~3분 걸리므로 Vercel 함수 제한을 늘린다 (Pro 플랜 필요)
// 기본 제한(무료 플랜 10초 등)보다 훨씬 길게 설정 — 7개 에이전트를 순차로
// LLM 호출하는 특성상 짧은 타임아웃이면 항상 실패한다.
export const maxDuration = 300

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const q = searchParams.get('q') ?? '이번 달 웹사이트 주요 지표와 이탈 원인을 분석해줘'

  try {
    // encodeURIComponent: 질문에 한글/특수문자가 포함되므로 URL 쿼리스트링에
    // 안전하게 넣기 위한 인코딩 — 이게 없으면 공백/특수문자에서 URL이 깨짐
    const res = await backendFetch(`/analyze?q=${encodeURIComponent(q)}`)
    const data = await res.json()
    // 백엔드가 반환한 status(200/422/500 등)를 그대로 프론트까지 전달 —
    // 프록시가 임의로 200으로 뭉개면 프론트가 QA_FAIL/EVAL_FAIL을 구분 못 한다
    return NextResponse.json(data, { status: res.status })
  } catch (err) {
    console.error(err)
    return NextResponse.json({ error: String(err) }, { status: 500 })
  }
}
