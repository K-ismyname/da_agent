'use client'

import { useEffect, useState } from 'react'

type Brief = {
  headline: string
  insights: { num: string; text: string }[]
  actions: string[]
  confidence: number
  qa_verdict: 'PASS' | 'WARN' | 'FAIL'
}

type Data = {
  kpi: { date: string; users: number; sessions: number; engagement_rate: number; scroll_rate: number; avg_engagement_time_sec: number; returning_users: number }[]
  funnel: { funnel_step: string; step_order: number; users: number; drop_off_rate: number }[]
  channel: { channel_group: string; sessions: number; users: number; engagement_rate: number }[]
  landing: { page_path: string; page_views: number; scroll_rate: number; avg_engagement_time_sec: number }[]
  cohort: { cohort_week: string; week_number: number; users: number; retention_rate: number }[]
}

const DEFAULT_QUESTION = '이번 달 웹사이트 주요 지표와 이탈 원인을 분석해줘'

// A/B 실험 질문은 여기서 제외 — 전용 /ab-test 페이지에서 가입 유도 배너 실험을 별도 제공.
// "어느 채널?" 류는 제외: UTM 미설정으로 Data Scientist가 항상 answerable=false 처리하므로
// (채널 데이터 신뢰도 LOW) 예시로 넣으면 반드시 "답할 수 없음"이 나온다.
const EXAMPLE_QUESTIONS = [
  '이번 달 웹사이트 주요 지표와 이탈 원인을 분석해줘',
  '퍼널에서 가장 많이 이탈하는 구간이 어디야?',
  '재방문율이 어떻게 되고 있어?',
  '사용자들이 주로 어떤 경로로 사이트를 이동해?',
  '어느 페이지 체류시간이 가장 길어?',
]

export default function Dashboard() {
  const [brief, setBrief] = useState<Brief | null>(null)
  const [data, setData] = useState<Data | null>(null)
  const [briefLoading, setBriefLoading] = useState(true)
  const [dataLoading, setDataLoading] = useState(true)
  const [question, setQuestion] = useState(DEFAULT_QUESTION)
  const [askedQuestion, setAskedQuestion] = useState(DEFAULT_QUESTION)
  const [briefError, setBriefError] = useState(false)

  // 차트 데이터: LLM 없이 마트 직접 조회 (30초 타임아웃)
  useEffect(() => {
    fetch('/api/data', { signal: AbortSignal.timeout(30_000) })
      .then(r => r.json())
      .then(res => { setData(res); setDataLoading(false) })
      .catch(() => setDataLoading(false))
  }, [])

  function runAnalysis(q: string) {
    setBriefLoading(true)
    setBriefError(false)
    setAskedQuestion(q)
    fetch(`/api/analyze?q=${encodeURIComponent(q)}`, { signal: AbortSignal.timeout(180_000) })
      .then(r => r.json())
      .then(res => {
        if (res.brief) setBrief(res.brief)
        else setBriefError(true)
        setBriefLoading(false)
      })
      .catch(() => { setBriefError(true); setBriefLoading(false) })
  }

  // AI 분석: 별도 요청 — LLM 파이프라인이 길어서 3분 타임아웃 (첫 로드 시 기본 질문 자동 실행)
  useEffect(() => { runAnalysis(DEFAULT_QUESTION) }, [])

  const loading = briefLoading && dataLoading

  // 퍼널 집계 — funnel_mart 단계명 기준 (2026-07-09 재설계: 방문→콘텐츠 소비→…→가입 완료)
  const funnelStart = data?.funnel.find(f => f.funnel_step === '방문')?.users ?? 0
  const funnelDone  = data?.funnel.find(f => f.funnel_step === '가입 완료')?.users ?? 0
  const convRate = funnelStart ? ((funnelDone / funnelStart) * 100).toFixed(1) : '0'

  // KPI 집계 (전체 기간 평균/합산)
  const kpiRows = data?.kpi ?? []
  const totalUsers    = kpiRows.reduce((s, r) => s + r.users, 0)
  const avgEngagement = kpiRows.length ? (kpiRows.reduce((s, r) => s + r.avg_engagement_time_sec, 0) / kpiRows.length) : 0
  const avgEngRate    = kpiRows.length ? (kpiRows.reduce((s, r) => s + r.engagement_rate, 0) / kpiRows.length) : 0

  return (
    <div className="min-h-screen bg-[#0f0f14] text-slate-200" style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>

      {/* Header */}
      <header className="border-b border-[#1e1e2e] bg-[#13131a] px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-white font-bold text-lg">DA Agent <span className="text-[#7c6af7]">/ 데이터 분석 멀티 에이전트</span></h1>
        </div>
        <div className="flex items-center gap-4">
          <a href="/ab-test" className="text-xs text-[#7c6af7] hover:text-violet-300 font-semibold">A/B Test Report →</a>
          {kpiRows.length > 0 && (
            <span className="text-xs text-slate-500">
              {kpiRows[0].date} — {kpiRows[kpiRows.length - 1].date}
            </span>
          )}
          {brief && (
            <span className={`text-xs px-2 py-1 rounded font-semibold ${
              brief.qa_verdict === 'PASS' ? 'bg-green-500/10 text-green-400 border border-green-500/20'
              : brief.qa_verdict === 'WARN' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
              : 'bg-red-500/10 text-red-400 border border-red-500/20'
            }`}>
              QA {brief.qa_verdict}
            </span>
          )}
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-8 py-8">

        {/* Agent Pipeline */}
        <div className="mb-8">
          <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-3">Agent Pipeline</div>
          <div className="flex items-center gap-1 overflow-x-auto pb-1">
            {['Supervisor', 'Product Analyst', 'Analytics Engineer', 'Data Scientist', 'QA Reviewer', 'Evaluator', 'Head of Data'].map((agent, i) => (
              <div key={agent} className="flex items-center shrink-0">
                <div className={`border rounded-lg px-3 py-2 text-xs ${i === 6 ? 'border-[#7c6af740] bg-[#7c6af708]' : 'border-[#1e1e2e] bg-[#13131a]'}`}>
                  <div className={`font-semibold ${i === 6 ? 'text-[#7c6af7]' : 'text-slate-300'}`}>{agent}</div>
                  <div className={`text-xs mt-0.5 ${i === 6 ? 'text-[#7c6af7]' : 'text-green-400'}`}>
                    {briefLoading ? '⏳ 실행 중' : '✓ 완료'}
                  </div>
                </div>
                {i < 6 && <span className="text-slate-700 mx-1">→</span>}
              </div>
            ))}
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          {[
            { label: '총 방문자', value: dataLoading ? '-' : totalUsers.toLocaleString(), sub: '전체 기간 합산' },
            { label: '가입 전환율', value: dataLoading ? '-' : `${convRate}%`, sub: '방문 → 가입 완료' },
            { label: '평균 체류시간', value: dataLoading ? '-' : `${Math.floor(avgEngagement / 60)}m ${Math.round(avgEngagement % 60)}s`, sub: '참여 세션 기준' },
            { label: '참여율', value: dataLoading ? '-' : `${(avgEngRate * 100).toFixed(1)}%`, sub: '참여 세션 / 전체 세션' },
          ].map(card => (
            <div key={card.label} className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-5">
              <div className="text-xs text-slate-500 uppercase tracking-wide font-medium mb-2">{card.label}</div>
              <div className="text-3xl font-bold text-white mb-1">{card.value}</div>
              <div className="text-xs text-slate-600">{card.sub}</div>
            </div>
          ))}
        </div>

        {/* Question Input */}
        <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-5 mb-4">
          <div className="text-xs text-slate-500 uppercase tracking-wide font-bold mb-3">질문 한 줄로 GA4 데이터 분석 받기</div>
          <form
            onSubmit={e => { e.preventDefault(); if (question.trim() && !briefLoading) runAnalysis(question.trim()) }}
            className="flex gap-2 mb-3"
          >
            <input
              value={question}
              onChange={e => setQuestion(e.target.value)}
              placeholder="예: 이번 달 이탈 원인이 뭐야?"
              disabled={briefLoading}
              className="flex-1 bg-[#0f0f14] border border-[#1e1e2e] rounded-lg px-4 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-[#7c6af7] disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={briefLoading || !question.trim()}
              className="bg-[#7c6af7] text-white text-sm font-semibold px-5 py-2 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed hover:bg-violet-500 transition-colors shrink-0"
            >
              {briefLoading ? '분석 중...' : '분석 요청'}
            </button>
          </form>
          <div className="flex gap-2 flex-wrap">
            {EXAMPLE_QUESTIONS.map(q => (
              <button
                key={q}
                onClick={() => { if (!briefLoading) { setQuestion(q); runAnalysis(q) } }}
                disabled={briefLoading}
                className="text-xs text-slate-400 bg-[#0f0f14] border border-[#1e1e2e] rounded-full px-3 py-1 hover:border-[#7c6af7] hover:text-[#7c6af7] disabled:opacity-40 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* AI Executive Brief */}
        <div className="bg-gradient-to-br from-[#13131a] to-[#1a1030] border border-[#7c6af730] rounded-xl p-7 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-8 h-8 rounded-lg bg-[#7c6af720] border border-[#7c6af740] flex items-center justify-center text-sm">🧠</div>
            <div className="text-xs text-[#7c6af7] font-bold uppercase tracking-wide">Head of Data · Executive Brief</div>
          </div>
          <div className="text-xs text-slate-500 mb-4">Q. {askedQuestion}</div>

          {briefLoading ? (
            <div className="text-slate-400 animate-pulse">AI 에이전트 분석 중... (7개 에이전트 순차 실행, 최대 3분)</div>
          ) : briefError ? (
            <div className="text-red-400 text-sm">분석 실패 또는 검증 미통과 (QA/Evaluator FAIL). 다른 질문으로 다시 시도해보세요.</div>
          ) : brief ? (
            <>
              <div className="text-xl font-bold text-white mb-5 leading-snug">{brief.headline}</div>
              <div className="grid grid-cols-3 gap-3 mb-5">
                {brief.insights.map(ins => (
                  <div key={ins.num} className="bg-[#0f0f1480] border border-[#1e1e2e] rounded-lg p-4">
                    <div className="text-xs text-[#7c6af7] font-bold mb-1">{ins.num}</div>
                    <div className="text-sm text-slate-400 leading-relaxed">{ins.text}</div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2 flex-wrap mb-4">
                {brief.actions.map((a, i) => (
                  <span key={i} className="text-xs bg-green-500/10 text-green-400 border border-green-500/20 px-3 py-1.5 rounded-lg font-medium">
                    {`${['①','②','③'][i]} ${a}`}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-3 pt-4 border-t border-[#1e1e2e]">
                <span className="text-xs text-slate-500">분석 신뢰도</span>
                <div className="flex-1 bg-[#1e1e2e] rounded h-1.5">
                  <div className="h-full rounded bg-gradient-to-r from-[#7c6af7] to-green-400" style={{ width: `${brief.confidence}%` }} />
                </div>
                <span className="text-xs text-green-400 font-bold">{brief.confidence}%</span>
              </div>
            </>
          ) : null}
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          {/* Funnel */}
          <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-6">
            <div className="text-xs text-slate-500 uppercase tracking-wide font-bold mb-1">전환 퍼널</div>
            <div className="text-xs text-slate-600 mb-5">funnel_mart</div>
            <div className="space-y-4">
              {data?.funnel.sort((a,b) => a.step_order - b.step_order).map((step, i) => {
                const maxUsers = data.funnel[0].users
                const pct = (step.users / maxUsers) * 100
                return (
                  <div key={step.funnel_step}>
                    <div className="flex justify-between text-sm mb-1.5">
                      <span className="text-slate-300 font-medium">{step.funnel_step}</span>
                      <span className="text-slate-500">{step.users.toLocaleString()}명</span>
                    </div>
                    <div className="bg-[#1e1e2e] rounded h-2">
                      <div className="h-full rounded bg-gradient-to-r from-[#7c6af7] to-violet-400" style={{ width: `${pct}%` }} />
                    </div>
                    {i > 0 && <div className="text-xs text-red-400 mt-1">↓ {(step.drop_off_rate * 100).toFixed(1)}% 이탈</div>}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Channel */}
          <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-6">
            <div className="text-xs text-slate-500 uppercase tracking-wide font-bold mb-1">채널별 유입</div>
            <div className="text-xs text-slate-600 mb-5">marketing_channel_mart</div>
            <div className="space-y-4">
              {data?.channel.sort((a,b) => b.sessions - a.sessions).map(ch => {
                const maxSessions = Math.max(...(data?.channel.map(c => c.sessions) ?? [1]))
                const pct = (ch.sessions / maxSessions) * 100
                return (
                  <div key={ch.channel_group}>
                    <div className="flex justify-between text-sm mb-1.5">
                      <span className="text-slate-300 font-medium">{ch.channel_group}</span>
                      <div className="text-right">
                        <span className="text-slate-500 text-xs">{ch.sessions.toLocaleString()} sessions</span>
                        <span className={`ml-2 text-xs font-semibold ${ch.engagement_rate > 0.6 ? 'text-green-400' : ch.engagement_rate > 0.5 ? 'text-yellow-400' : 'text-red-400'}`}>
                          {(ch.engagement_rate * 100).toFixed(0)}% 참여율
                        </span>
                      </div>
                    </div>
                    <div className="bg-[#1e1e2e] rounded h-2">
                      <div className="h-full rounded bg-gradient-to-r from-[#7c6af7] to-violet-400" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Landing Pages + Cohort */}
        <div className="grid grid-cols-2 gap-4">
          {/* Landing Pages */}
          <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-6">
            <div className="text-xs text-slate-500 uppercase tracking-wide font-bold mb-1">페이지별 체류시간</div>
            <div className="text-xs text-slate-600 mb-5">landing_page_mart</div>
            <div className="space-y-3">
              {data?.landing.sort((a,b) => b.avg_engagement_time_sec - a.avg_engagement_time_sec).map(page => {
                const maxTime = Math.max(...(data?.landing.map(p => p.avg_engagement_time_sec) ?? [1]))
                const pct = (page.avg_engagement_time_sec / maxTime) * 100
                return (
                  <div key={page.page_path}>
                    <div className="flex justify-between mb-1">
                      <span className="text-slate-400 text-xs font-mono">{page.page_path}</span>
                      <span className="text-slate-500 text-xs">{page.avg_engagement_time_sec}s</span>
                    </div>
                    <div className="bg-[#1e1e2e] rounded h-1.5">
                      <div className="h-full rounded bg-gradient-to-r from-[#7c6af7] to-violet-400" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Cohort */}
          <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-6">
            <div className="text-xs text-slate-500 uppercase tracking-wide font-bold mb-1">코호트 재방문율</div>
            <div className="text-xs text-slate-600 mb-5">cohort_mart</div>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-[#1e1e2e]">
                  <th className="text-left pb-2 font-medium">코호트</th>
                  <th className="text-center pb-2 font-medium">W0</th>
                  <th className="text-center pb-2 font-medium">W1</th>
                  <th className="text-center pb-2 font-medium">W2</th>
                  <th className="text-center pb-2 font-medium">W3</th>
                </tr>
              </thead>
              <tbody>
                {Array.from(new Set(data?.cohort.map(c => c.cohort_week))).map(week => {
                  const rows = data?.cohort.filter(c => c.cohort_week === week) ?? []
                  return (
                    <tr key={week} className="border-b border-[#1e1e2e]">
                      <td className="py-2 text-slate-400">{week.slice(5)}</td>
                      {[0,1,2,3].map(w => {
                        const row = rows.find(r => r.week_number === w)
                        const rate = row ? Math.round(row.retention_rate * 100) : null
                        const color = rate === null ? '' : rate > 30 ? 'text-green-400' : rate > 20 ? 'text-yellow-400' : 'text-red-400'
                        return (
                          <td key={w} className={`text-center py-2 font-semibold ${color}`}>
                            {rate !== null ? `${rate}%` : '-'}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  )
}
