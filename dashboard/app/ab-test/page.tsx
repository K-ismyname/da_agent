'use client'

import { useEffect, useState } from 'react'

type VariantRow = {
  variant: string
  start_date: { value: string } | string
  end_date: { value: string } | string
  users_exposed: number; banner_shown: number; banner_click: number
  apply_reached: number; bounced: number
  apply_rate_pct: number; bounce_rate_pct: number; banner_ctr_pct: number | null
}

type DailyRow = { date: string; variant: string; apply_rate_pct: number; bounce_rate_pct: number }

const FUNNEL_STEPS: { key: keyof VariantRow; label: string }[] = [
  { key: 'users_exposed', label: '트리거 조건 노출 (스크롤 90%/행동 시도)' },
  { key: 'apply_reached', label: '/apply 도달' },
]

function lift(a: number, b: number) {
  return a ? (((b - a) / a) * 100).toFixed(1) : '-'
}

function dateStr(d: { value: string } | string) {
  return typeof d === 'string' ? d : d?.value ?? ''
}

function TrendChart({ daily, metric, label }: { daily: DailyRow[]; metric: 'apply_rate_pct' | 'bounce_rate_pct'; label: string }) {
  const dates = Array.from(new Set(daily.map(d => d.date)))
  const a = dates.map(dt => daily.find(d => d.date === dt && d.variant.startsWith('A'))?.[metric] ?? 0)
  const b = dates.map(dt => daily.find(d => d.date === dt && d.variant.startsWith('B'))?.[metric] ?? 0)
  const max = Math.max(...a, ...b, 0.001)
  const W = 560, H = 140
  const pts = (arr: number[]) =>
    arr.map((v, i) => `${(i / Math.max(arr.length - 1, 1)) * W},${H - (v / max) * (H - 10)}`).join(' ')
  return (
    <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-6">
      <div className="text-xs text-slate-500 uppercase tracking-wide font-bold mb-1">{label} 일별 추이</div>
      <div className="text-xs text-slate-600 mb-4">signup_prompt_experiment_mart · <span className="text-slate-400">A</span> vs <span className="text-[#7c6af7]">B</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <polyline points={pts(a)} fill="none" stroke="#64748b" strokeWidth="1.5" />
        <polyline points={pts(b)} fill="none" stroke="#7c6af7" strokeWidth="2" />
      </svg>
      <div className="flex justify-between text-xs text-slate-600 mt-1">
        <span>{dates[0]}</span><span>{dates[dates.length - 1]}</span>
      </div>
    </div>
  )
}

export default function AbTestReport() {
  const [summary, setSummary] = useState<VariantRow[] | null>(null)
  const [daily, setDaily] = useState<DailyRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/ab-test')
      .then(r => r.json())
      .then(res => { setSummary(res.summary); setDaily(res.daily ?? []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const A = summary?.find(v => v.variant.startsWith('A'))
  const B = summary?.find(v => v.variant.startsWith('B'))

  const primaryDegraded = A && B ? B.apply_rate_pct <= A.apply_rate_pct : false
  const guardrailDegraded = A && B ? B.bounce_rate_pct > A.bounce_rate_pct * 1.1 : false
  const winner = A && B && !primaryDegraded && !guardrailDegraded ? 'B — 능동 노출' : 'HOLD'

  return (
    <div className="min-h-screen bg-[#0f0f14] text-slate-200" style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }}>
      <header className="border-b border-[#1e1e2e] bg-[#13131a] px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-white font-bold text-lg">A/B Test Report <span className="text-[#7c6af7]">/ 가입 유도 배너</span></h1>
          <span className="text-xs bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 px-3 py-1 rounded-full font-semibold">목업 데이터</span>
        </div>
        <div className="flex items-center gap-4">
          <a href="/" className="text-xs text-slate-500 hover:text-slate-300">← 메인 대시보드</a>
          {A && <span className="text-xs text-slate-500">{dateStr(A.start_date)} — {dateStr(A.end_date)}</span>}
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-8 pt-4">
        <div className="text-xs text-slate-500 bg-[#13131a] border border-[#1e1e2e] rounded-lg px-4 py-2">
          이 페이지는 이 커뮤니티의 실제 실험(아티클 스크롤 90% 시점에 가입 유도 배너를 능동적으로
          노출할지)을 측정합니다. A: 저장/댓글/팔로우 시도 시에만 수동 노출(현행) · B: 스크롤 시점 능동 노출(변형).
          배너 기능이 아직 실배포 전이라 <strong className="text-slate-400">목업 데이터</strong>이며,
          실배포 후 GA4 실데이터로 교체됩니다. (Meta Ads 스터디 자료 기반 A/B 리포트는 제거됨 — 이 커뮤니티와 무관한 데모였음)
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-8 py-8">
        {loading && <div className="text-slate-400 animate-pulse">signup_prompt_experiment_mart 조회 중...</div>}
        {!loading && !A && <div className="text-red-400 text-sm">signup_prompt_experiment_mart가 없습니다. `python agent_backend/scripts/build_signup_prompt_experiment_mart.py`를 먼저 실행하세요.</div>}

        {A && B && (
          <>
            {/* Recommended Variant */}
            <div className="bg-gradient-to-br from-[#13131a] to-[#1a1030] border border-[#7c6af730] rounded-xl p-7 mb-6">
              <div className="text-xs text-[#7c6af7] font-bold uppercase tracking-wide mb-2">Recommended Variant</div>
              <div className="text-3xl font-bold text-white mb-2">{winner}</div>
              <div className="text-sm text-slate-400">
                Primary 지표(Apply Reach Rate)와 Guardrail 지표(Bounce Rate)를 함께 판단한 결과입니다.
                통계적 유의성(p-value)은 에이전트 파이프라인(run_significance_test(experiment=&quot;signup_prompt&quot;))에서 검증됩니다.
              </div>
            </div>

            {/* Primary Metric */}
            <div className="text-xs text-slate-500 uppercase tracking-widest font-bold mb-3">Primary Metric — GO / NO-GO</div>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-5">
                <div className="text-xs text-slate-500 uppercase tracking-wide font-medium mb-2">Apply Reach Rate</div>
                <div className="flex items-end gap-4 mb-1">
                  <div><div className="text-xs text-slate-600">A</div><div className="text-xl font-bold text-slate-400">{A.apply_rate_pct}%</div></div>
                  <div><div className="text-xs text-[#7c6af7]">B</div><div className="text-2xl font-bold text-white">{B.apply_rate_pct}%</div></div>
                </div>
                <div className={`text-xs font-semibold ${!primaryDegraded ? 'text-green-400' : 'text-red-400'}`}>
                  {lift(A.apply_rate_pct, B.apply_rate_pct)}% lift {!primaryDegraded ? '✓ B 우세' : '✗ A 우세'}
                </div>
              </div>

              {/* Guardrail */}
              <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-5">
                <div className="text-xs text-slate-500 uppercase tracking-wide font-medium mb-2">Bounce Rate (Guardrail)</div>
                <div className="flex items-end gap-4 mb-1">
                  <div><div className="text-xs text-slate-600">A</div><div className="text-lg font-bold text-slate-400">{A.bounce_rate_pct}%</div></div>
                  <div><div className="text-xs text-[#7c6af7]">B</div><div className="text-lg font-bold text-white">{B.bounce_rate_pct}%</div></div>
                </div>
                <div className={`text-xs font-semibold ${guardrailDegraded ? 'text-red-400' : 'text-green-400'}`}>
                  {guardrailDegraded ? '⚠ DEGRADED (>10% 악화)' : '✓ OK'}
                </div>
              </div>

              {/* Info (B-only) */}
              <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-5">
                <div className="text-xs text-slate-500 uppercase tracking-wide font-medium mb-2">Banner CTR (Info, B만)</div>
                <div className="text-2xl font-bold text-white mb-1">{B.banner_ctr_pct ?? '-'}%</div>
                <div className="text-xs text-slate-600">A는 배너 자체가 없어 측정 대상 아님</div>
              </div>
            </div>

            {/* Funnel comparison */}
            <div className="bg-[#13131a] border border-[#1e1e2e] rounded-xl p-6 mb-6">
              <div className="text-xs text-slate-500 uppercase tracking-wide font-bold mb-1">퍼널 비교 — 노출 → 가입 도달</div>
              <div className="text-xs text-slate-600 mb-5">signup_prompt_experiment_mart · 절대 수치 + 단계 전환율</div>
              <div className="space-y-4">
                {FUNNEL_STEPS.map((step, i) => {
                  const aV = A[step.key] as number, bV = B[step.key] as number
                  const maxV = Math.max(A[FUNNEL_STEPS[0].key] as number, B[FUNNEL_STEPS[0].key] as number)
                  const aPrev = i > 0 ? (A[FUNNEL_STEPS[i - 1].key] as number) : aV
                  const bPrev = i > 0 ? (B[FUNNEL_STEPS[i - 1].key] as number) : bV
                  return (
                    <div key={step.label}>
                      <div className="flex justify-between text-sm mb-1.5">
                        <span className="text-slate-300 font-medium">{step.label}</span>
                        <span className="text-xs text-slate-500">
                          A {aV.toLocaleString()} {i > 0 && `(${((aV / aPrev) * 100).toFixed(1)}%)`} ·{' '}
                          <span className="text-[#7c6af7]">B {bV.toLocaleString()} {i > 0 && `(${((bV / bPrev) * 100).toFixed(1)}%)`}</span>
                        </span>
                      </div>
                      <div className="bg-[#1e1e2e] rounded h-2 mb-1">
                        <div className="h-full rounded bg-slate-500" style={{ width: `${(aV / maxV) * 100}%` }} />
                      </div>
                      <div className="bg-[#1e1e2e] rounded h-2">
                        <div className="h-full rounded bg-gradient-to-r from-[#7c6af7] to-violet-400" style={{ width: `${(bV / maxV) * 100}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Daily trends */}
            <div className="grid grid-cols-2 gap-4">
              <TrendChart daily={daily} metric="apply_rate_pct" label="Apply Reach Rate (%)" />
              <TrendChart daily={daily} metric="bounce_rate_pct" label="Bounce Rate (%)" />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
